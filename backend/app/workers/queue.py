"""arq Redis connection pool for enqueueing jobs from the API process.

Mirrors app/db/session.py's lazy-singleton pattern. The worker process itself
(started via `arq app.workers.settings.WorkerSettings`) manages its own
connection separately — this pool is only for the API side, pushing jobs in.
"""

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings

_pool: ArqRedis | None = None


async def get_arq_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        settings = get_settings()
        if not settings.redis_url:
            raise RuntimeError(
                "REDIS_URL is not configured. Set it in .env before uploading documents "
                "(document processing requires the background job queue)."
            )
        _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _pool
