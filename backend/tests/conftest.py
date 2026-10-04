"""Shared test fixtures.

These are integration tests against real PostgreSQL and Redis instances (see
ADR-001 and ADR-007 — fakes/mocks for either would hide real behavior these
tests exist to catch). DATABASE_URL/REDIS_URL/STORAGE_ROOT are all overridden
to dedicated test locations before anything in `app` is imported, so the test
suite never touches dev data:
  - Postgres: separate database (enterprise_ai_platform_test)
  - Redis: separate logical DB index (15) on the same server
  - File storage: a fresh temp directory, removed at the end of the run
"""

import os
import shutil
import tempfile

_TEST_STORAGE_ROOT = tempfile.mkdtemp(prefix="enterprise_ai_platform_test_uploads_")

os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://postgres:postgres@localhost:5432/enterprise_ai_platform_test"
)
os.environ["REDIS_URL"] = "redis://localhost:6379/15"
os.environ["STORAGE_ROOT"] = _TEST_STORAGE_ROOT
os.environ["JWT_SECRET"] = "test-only-secret-4f9c2a7e1b3d6f8091a2c4e6b8d0f1a3"
# Explicit, not left to whatever a local .env happens to contain: debug=True
# makes Starlette bypass the custom JSON exception handler entirely for
# unhandled exceptions (see app/core/config.py's comment) — tests that check
# error response shape (test_error_handling.py) depend on this being False
# regardless of ambient environment state.
os.environ["DEBUG"] = "false"
# Same rationale as DEBUG above: explicit, not left to ambient .env state.
# test_anthropic_provider.py's missing-key test depends on this actually
# being unset regardless of what a local .env happens to contain.
os.environ["ANTHROPIC_API_KEY"] = ""
# Disabled by default so the existing test suite (much of which makes many
# requests per test — document processing, multi-step agent flows) isn't
# affected by rate limiting it isn't testing. Limits are still set low here
# (not left at production defaults) so tests/test_rate_limit_api.py, which
# explicitly re-enables rate_limiting_enabled per test via a dependency
# override, can trigger a 429 with a handful of requests rather than dozens
# — see that file for why only the enabled flag (not these numeric limits)
# can be overridden per-test at all: the limit/window values are baked into
# each route's dependency closure at module-import time, not re-read from
# settings per request.
os.environ["RATE_LIMITING_ENABLED"] = "false"
os.environ["RATE_LIMIT_LOGIN_PER_MINUTE"] = "3"
os.environ["RATE_LIMIT_REGISTER_PER_HOUR"] = "3"
os.environ["RATE_LIMIT_FAILED_LOGIN_ATTEMPTS"] = "3"
os.environ["RATE_LIMIT_FAILED_LOGIN_WINDOW_SECONDS"] = "60"
os.environ["RATE_LIMIT_UPLOAD_PER_HOUR"] = "3"
os.environ["RATE_LIMIT_SEARCH_PER_MINUTE"] = "3"
os.environ["RATE_LIMIT_CHAT_PER_MINUTE"] = "3"
os.environ["RATE_LIMIT_AGENT_RUN_PER_HOUR"] = "3"

from collections.abc import AsyncGenerator  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()
_settings = get_settings()
assert _settings.database_url is not None

import app.core.rate_limit as rate_limit_module  # noqa: E402
import app.db.session as db_session_module  # noqa: E402
import app.models  # noqa: E402,F401  (registers all models on Base.metadata)
import app.workers.queue as arq_queue_module  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.embeddings.factory import get_embedding_provider  # noqa: E402
from app.services.llm.factory import get_llm_provider  # noqa: E402
from app.services.reranking.factory import get_reranker  # noqa: E402
from tests.fakes import FakeEmbeddingProvider, FakeLLMProvider, FakeReranker  # noqa: E402


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    shutil.rmtree(_TEST_STORAGE_ROOT, ignore_errors=True)


@pytest.fixture(autouse=True)
async def _reset_production_db_singleton() -> AsyncGenerator[None]:
    """`process_document` (the worker task) deliberately uses the same
    process-wide singleton engine as the real API/worker processes would
    (app/db/session.py) — that's the correct pattern for a long-running
    process bound to one event loop. But tests call the task function
    directly on a fresh per-test event loop, so — same rationale as
    _reset_arq_pool below — the singleton must be rebuilt per test or it
    binds to a closed loop.
    """
    db_session_module._engine = None
    db_session_module._session_factory = None
    yield
    if db_session_module._engine is not None:
        await db_session_module._engine.dispose()
        db_session_module._engine = None
        db_session_module._session_factory = None


@pytest.fixture
async def db_engine() -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(_settings.database_url, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=db_engine, expire_on_commit=False, autoflush=False)


@pytest.fixture(autouse=True)
async def _clean_database(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[None]:
    """Deletes parent rows before each test; ON DELETE CASCADE clears
    dependents (memberships, refresh_tokens, documents) so every test starts
    empty.
    """
    async with session_factory() as session:
        await session.execute(Base.metadata.tables["organizations"].delete())
        await session.execute(Base.metadata.tables["users"].delete())
        await session.commit()
    yield


@pytest.fixture(autouse=True)
async def _reset_arq_pool() -> AsyncGenerator[None]:
    """The arq Redis pool is a process-wide singleton (see workers/queue.py),
    same rationale as the DB engine — but pytest-asyncio gives each test its
    own event loop, so a pool created in one test's loop breaks in the next.
    Force a fresh pool per test, and flush the test Redis DB afterwards so
    jobs don't pile up across a whole test run (nothing consumes them here —
    processing is tested by calling the task function directly, not by
    running a live worker against the queue).
    """
    arq_queue_module._pool = None
    yield
    if arq_queue_module._pool is not None:
        pool = arq_queue_module._pool
        await pool.flushdb()
        await pool.aclose()


@pytest.fixture(autouse=True)
async def _reset_rate_limit_client() -> AsyncGenerator[None]:
    """Same event-loop-per-test issue as _reset_arq_pool above, for the rate
    limiter's own Redis connection (app/core/rate_limit.py).

    Unlike _reset_arq_pool's flush, this one is unconditional: a test that
    never happens to create a rate-limit Redis client still needs any
    counters a *previous* test left behind cleared before it runs (relying
    on _reset_arq_pool's flush isn't enough — that flush only fires if the
    arq pool itself was touched during that specific test, which a
    rate-limit-only test never does, so counters were silently leaking
    across tests until this was made unconditional).
    """
    rate_limit_module._client = None
    connection = await rate_limit_module.get_rate_limit_redis()
    await connection.flushdb()
    yield
    await connection.flushdb()
    await connection.aclose()
    rate_limit_module._client = None


@pytest.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient]:
    async def _override_get_db() -> AsyncGenerator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    # Every API test uses fake embedding/reranking/LLM providers — see
    # ADR-008/009/010 for why the real implementations can't run
    # authenticated calls in this sandbox (no API key, blocked model hosts,
    # or disk budget, depending on the provider). Real pipeline correctness
    # (Postgres, pgvector, full-text search, score fusion, citation
    # validation) is still fully exercised; only the third-party model calls
    # are swapped for deterministic equivalents, the same DI seam production
    # code uses for the real ones.
    app.dependency_overrides[get_embedding_provider] = lambda: FakeEmbeddingProvider()
    app.dependency_overrides[get_reranker] = lambda: FakeReranker()
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_embedding_provider, None)
        app.dependency_overrides.pop(get_reranker, None)
        app.dependency_overrides.pop(get_llm_provider, None)
