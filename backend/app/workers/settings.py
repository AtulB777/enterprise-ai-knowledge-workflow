from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.workers.tasks import process_document


def _redis_settings() -> RedisSettings:
    settings = get_settings()
    if not settings.redis_url:
        raise RuntimeError("REDIS_URL must be set to run the worker.")
    return RedisSettings.from_dsn(settings.redis_url)


async def _on_startup(ctx: dict[str, object]) -> None:
    # The worker process never imports app.main, so nothing else configures
    # structured JSON logging for it — without this, worker logs (including
    # exception tracebacks from failed jobs) are plain, inconsistent text
    # instead of the same machine-parseable format the API process uses.
    configure_logging()


class WorkerSettings:
    functions = [process_document]
    on_startup = _on_startup
    redis_settings = _redis_settings()
    # Ingestion jobs do real I/O (extraction, OCR) — bound how long a single
    # stuck job can hold a worker slot rather than letting it run forever.
    job_timeout = 300
    # arq's own default here is 0 — genuinely abrupt shutdown (in-progress
    # jobs get cancelled immediately on SIGTERM), confirmed by reading
    # arq's Worker.__init__ directly, not assumed from documentation. 30s
    # gives a typical in-progress document-processing job a real chance to
    # finish cleanly on a graceful restart/deploy, without making every
    # shutdown wait as long as the full job_timeout. Coordinated with
    # docker-compose.yml's worker service stop_grace_period (ADR-020) —
    # Docker's own SIGKILL grace period must be at least this long, or it
    # would cut this wait short regardless of what's configured here.
    job_completion_wait = 30
