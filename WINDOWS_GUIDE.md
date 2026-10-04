# Windows 11 Setup & Execution Guide

Practical, Windows-specific instructions for getting this project running
and using it day to day. This complements — doesn't replace —
[`SETUP_GUIDE.md`](SETUP_GUIDE.md), [`EXECUTION_GUIDE.md`](EXECUTION_GUIDE.md),
and [`IMPLEMENTATION_GUIDE.md`](IMPLEMENTATION_GUIDE.md), which are written
generically (mostly bash/Linux syntax) and stay accurate for the
architecture itself regardless of your OS — this guide is specifically
about the parts that differ on Windows.

## The short version

**Use Docker Desktop.** This project has five services (Postgres, Redis,
the API, a background worker, the frontend) that would each need separate
native-Windows installation and configuration if run without Docker — and
two of them (Redis and pgvector) are genuinely awkward on native Windows
(more on why below). Docker Desktop sidesteps all of that: every service
runs as a Linux container regardless of your host OS, so the exact same
`docker-compose.yml` this project ships with just works. This is the path
below in full; skip to [Path B](#path-b-wsl2--manual-setup-for-active-development)
only if you actually intend to edit the code.

---

## Path A: Docker Desktop (recommended)

### 1. Install Docker Desktop

Download from [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/)
and run the installer. During setup, keep **"Use WSL 2 instead of
Hyper-V"** checked (the default on Windows 11) — this is faster and is
what the rest of this guide assumes.

If your system doesn't already have WSL2, the Docker Desktop installer
will prompt you to enable it, which may require one restart. If you'd
rather do it yourself first: open PowerShell **as Administrator** and run

```powershell
wsl --install
```

then restart. Afterward, launch Docker Desktop from the Start menu and
wait for its status icon (bottom-left of the window, or the system tray
icon) to say **"Docker Desktop is running."** Everything below needs this
running in the background the whole time.

### 2. Get the project onto your machine

If you downloaded a `.zip`: right-click it → **Extract All...** → pick a
folder (avoid deeply nested paths or folders with spaces, e.g. prefer
`C:\dev\project` over `C:\Users\you\Documents\My Projects\project`).

Open **PowerShell** or **Windows Terminal**, then navigate there:

```powershell
cd C:\dev\project
```

### 3. Configure environment variables

```powershell
Copy-Item .env.example .env
notepad .env
```

At minimum, set a real `JWT_SECRET`. Windows doesn't have `openssl` on
`PATH` by default (Git for Windows does bundle it, if you have that
installed — `openssl rand -hex 32` in Git Bash works fine). Without that,
generate an equivalent random 32-byte hex string directly in PowerShell:

```powershell
-join ((1..32) | ForEach-Object { "{0:x2}" -f (Get-Random -Maximum 256) })
```

Copy the output into `.env` as the value for `JWT_SECRET`. Leave
`ENVIRONMENT=development` — the app deliberately refuses to start with
the default secret if this is set to `production` (see
`docs/adr/ADR-020-production-readiness.md`).

Also decide on an LLM provider in the same file (needed for chat and
agent runs — everything else works without one):

```ini
# Option A: Ollama running on your Windows host
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
# host.docker.internal is how a container reaches the Windows host itself
# — "localhost" from inside a container means the container, not your PC.

# Option B: Anthropic
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-...
```

If choosing Ollama: install it from [ollama.com](https://ollama.com) for
Windows, then in PowerShell: `ollama pull llama3.1:8b` (or whichever
model you set `OLLAMA_MODEL` to).

### 4. Start everything

```powershell
docker compose up --build
```

First run builds both application images and downloads the Postgres/
Redis base images — expect several minutes depending on your connection.
Leave this terminal open (or add `-d` to run detached:
`docker compose up --build -d`, then use `docker compose logs -f` when you
want to watch output).

The `api` service runs database migrations automatically before it starts
serving, and `worker` waits for `api` to report healthy before starting
itself — you don't need to run any setup steps by hand.

### 5. Verify it's working

- Frontend: open http://localhost:3000 in a browser
- API: http://localhost:8000/api/v1/health should return
  `{"status":"ok",...}`
- Register an account at http://localhost:3000/register, upload a
  document, and try asking a question about it in Chat

If a port (3000, 8000, 5432, 6379) is already in use by something else on
your machine, `docker compose up` will fail with a clear "port is already
allocated" error — either stop whatever's using it, or edit the `ports:`
mapping in `docker-compose.yml` (the left-hand side of each `"3000:3000"`
pair is the port on *your* machine; change that one, leave the container
side alone).

### Everyday commands

```powershell
docker compose up -d           # start in the background
docker compose ps              # check status of every service
docker compose logs -f api     # follow one service's logs (Ctrl+C to stop watching)
docker compose down            # stop everything
docker compose down -v         # stop and also delete stored data (documents, DB)
```

---

## Path B: WSL2 + manual setup (for active development)

If you're going to actually edit the backend or frontend code, running
everything natively inside WSL2 (rather than through Docker) gives you a
tighter edit-test loop and — importantly — a genuinely Linux environment,
which sidesteps every Windows-native complication below. This is a real
Linux filesystem and process environment, not an emulation layer.

```powershell
wsl --install -d Ubuntu
```

Restart if prompted, then open the new **Ubuntu** app from the Start
menu (this is a real terminal into a Linux environment running
alongside Windows). From here, follow [`SETUP_GUIDE.md`](SETUP_GUIDE.md)'s
**Path B (Manual Setup)** exactly as written — every command there is
bash for a Debian/Ubuntu-family system, which is precisely what you now
have. Your project files are reachable from WSL2 at
`/mnt/c/dev/project` (adjust for wherever you actually extracted them on
the Windows side), or — for meaningfully better filesystem performance —
consider copying the project into WSL2's own filesystem instead (e.g.
`~/project`) and editing it from there using VS Code's
[Remote - WSL extension](https://code.visualstudio.com/docs/remote/wsl),
which lets you use a normal Windows-side VS Code window against files that
physically live inside WSL2.

---

## Path C: Native Windows, no WSL2, no Docker (possible, not recommended)

Genuinely possible, but this stack has three real, specific points of
friction on native Windows that Path A/B avoid entirely:

- **Redis has no officially supported native Windows build.** Microsoft's
  old port is unmaintained. Practical options: [Memurai](https://www.memurai.com/)
  (a Windows-native Redis-compatible server, free tier available), or just
  run Redis via Docker even if you run everything else natively
  (`docker run -d -p 6379:6379 redis:7-alpine`).
- **pgvector doesn't have an official prebuilt Windows installer** the way
  it does for Linux/Mac package managers — building it from source on
  Windows needs the Visual Studio C++ build tools and is meaningfully more
  involved than `apt install postgresql-16-pgvector`.
- **`python-magic` (file-type detection, `core/file_validation.py`)
  expects a `libmagic` shared library that Windows doesn't ship.** Install
  `python-magic-bin` instead (`pip install python-magic-bin`, in addition
  to what's in `requirements.txt`) — it bundles the needed DLLs. Without
  this, document upload will fail at the MIME-sniffing step specifically.

If you still want this path: install Python 3.12 and Node.js 22 from
their official Windows installers, PostgreSQL from
[postgresql.org](https://www.postgresql.org/download/windows/) (then
build pgvector per its own Windows instructions, or use a prebuilt image
via Docker just for that one piece), get Redis running via one of the
options above, then follow the same steps as
[`SETUP_GUIDE.md`](SETUP_GUIDE.md)'s manual path with these PowerShell
adjustments:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1        # not "source .venv/bin/activate"
pip install -r requirements.txt
pip install python-magic-bin       # the Windows-specific addition above

Copy-Item ..\.env.example .env
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

(If PowerShell refuses to run the activation script with an "execution
policy" error: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`,
run once, as yourself, not as Administrator.)

Tesseract OCR (for scanned-PDF text extraction) needs its own
[Windows installer](https://github.com/UB-Mannheim/tesseract/wiki), and
its install directory added to your `PATH` (or set
`pytesseract.pytesseract.tesseract_cmd` explicitly — not something this
project's code currently does for you, since it assumes a Linux
deployment target per `docs/adr/ADR-019-docker-compose.md`).

---

## Backup/restore scripts on Windows

`scripts/backup.sh` and `scripts/restore.sh` are POSIX shell scripts —
they don't run directly in PowerShell or Command Prompt. Run them from
either a WSL2 terminal or Git Bash (both can reach `docker compose` on
your Windows-side Docker Desktop installation directly, no extra
configuration needed). One real, Windows-specific trap: if Git checked
these out with `core.autocrlf` converting line endings to CRLF, WSL2/Git
Bash will fail to run them with a `$'\r': command not found`-style error.
Check and fix if needed:

```bash
file scripts/backup.sh          # "with CRLF line terminators" means you have this problem
sed -i 's/\r$//' scripts/backup.sh scripts/restore.sh
```

---

## Windows-specific troubleshooting

| Symptom | Likely cause |
|---|---|
| `docker compose up` fails immediately, mentions the daemon isn't running | Docker Desktop isn't started, or is still starting — check its tray icon |
| `docker compose up` fails with a WSL-related error | WSL2 isn't installed/enabled — see the `wsl --install` step above, then restart |
| Everything starts, but Ollama-based chat/agent calls fail | Used `localhost` instead of `host.docker.internal` for `OLLAMA_BASE_URL` — from inside a container, `localhost` refers to the container itself, not your Windows host |
| `docker compose up` fails with "port is already allocated" | Something else on Windows is already using that port — see step 5 above |
| Windows Defender Firewall prompts about Docker on first run | Expected the first time Docker Desktop starts its networking — allow it on private networks |
| A `.sh` script fails with a `$'\r'` error in WSL2/Git Bash | CRLF line endings from a Windows-side git checkout — see the fix just above |
| PowerShell won't run `.venv\Scripts\Activate.ps1` | Execution policy — see the `Set-ExecutionPolicy` note in Path C above |

For anything not covered here — application-level issues rather than
Windows-specific ones — see the troubleshooting tables in
[`SETUP_GUIDE.md`](SETUP_GUIDE.md) and [`EXECUTION_GUIDE.md`](EXECUTION_GUIDE.md).
