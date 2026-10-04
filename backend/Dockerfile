# syntax=docker/dockerfile:1

# --- Builder: full toolchain, installs the real, complete requirements.txt
# (including sentence-transformers) - unlike every pip install this project's
# own sandbox has run, which always excluded it for disk-space reasons. This
# image is the actual intended deployment artifact (ADR-019, Consequences).
FROM python:3.12-slim AS builder

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# --- Runtime: slim image, only what's needed to actually run the app.
FROM python:3.12-slim AS runtime

# Real runtime system dependencies, not build-time-only ones:
# - libmagic1: python-magic's file-type sniffing (app/core/file_validation.py)
# - tesseract-ocr: pytesseract's OCR fallback for scanned PDFs (app/services/extraction.py)
# - libpq5: asyncpg's underlying libpq client library
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libmagic1 \
        tesseract-ocr \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash app
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY --chown=app:app . .
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

RUN mkdir -p /app/data/uploads && chown -R app:app /app/data
USER app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" || exit 1

# Migrations run here, not baked into a separate init container (ADR-019
# decision 2) - only the api service's entrypoint does this; the worker
# service overrides CMD entirely (arq, no migration step) and waits for
# api's healthcheck first, so it never races this.
ENTRYPOINT ["docker-entrypoint.sh"]
# --timeout-graceful-shutdown: uvicorn's own default is unbounded (waits
# indefinitely for in-flight requests, confirmed by reading server.py
# directly) - 30s is a deliberate, bounded value, coordinated with
# docker-compose.yml's stop_grace_period for this service (ADR-020). Chosen
# knowing it won't fully protect an in-flight agent call, which can
# legitimately run up to MAX_RUNTIME_SECONDS (90s, ADR-012) - a real,
# acknowledged trade-off between shutdown speed and in-flight request
# safety, not silently glossed over.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "30"]
