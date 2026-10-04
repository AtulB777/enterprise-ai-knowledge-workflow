"""Central application configuration.

All configuration is loaded from environment variables (and a local .env file in
development). Only variables genuinely required for the app to start are marked
required — everything else has a safe default so the app gives a clear error only
when a feature that actually needs the missing config is used, not on startup.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_name: str = "Enterprise AI Knowledge & Workflow Platform"
    environment: Literal["development", "test", "production"] = "development"
    api_v1_prefix: str = "/api/v1"
    debug: bool = False

    # --- CORS ---
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # --- Database (wired up in Phase 3; optional here so the app can still boot
    # for a health check during scaffolding without a running Postgres) ---
    database_url: str | None = None

    # --- Redis (used by the background worker from Phase 4 onward) ---
    redis_url: str | None = None

    # --- File storage (Phase 4) ---
    storage_root: str = "./data/uploads"
    max_upload_size_mb: int = 25

    # --- LLM provider (Phase 7) ---
    llm_provider: Literal["ollama", "openai", "anthropic", "gemini"] = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    anthropic_model: str = "claude-sonnet-4-5-20250929"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None

    # --- RAG generation (Phase 7) ---
    rag_max_context_chars: int = 12000
    rag_max_response_tokens: int = 1024

    # --- Agent system (Phase 9) ---
    # Kept deliberately small — synchronous execution model (ADR-012
    # decision 2), so these bound how long a single HTTP request can run.
    agent_max_steps: int = 8
    agent_max_runtime_seconds: int = 90
    agent_max_tool_calls: int = 6
    agent_planner_max_tokens: int = 1024

    # --- Rate limiting (Phase 14, spec §39, ADR-017) ---
    rate_limiting_enabled: bool = True
    # Pre-auth, IP-based (ADR-017 decision 3).
    rate_limit_login_per_minute: int = 20
    rate_limit_register_per_hour: int = 5
    # Failed-login-specific throttling, keyed by email not IP (ADR-017
    # decision 4) — deliberately tighter and a longer window than the
    # general login route limit above, since this targets one specific
    # account rather than overall traffic.
    rate_limit_failed_login_attempts: int = 5
    rate_limit_failed_login_window_seconds: int = 900
    # Authenticated, user-based.
    rate_limit_upload_per_hour: int = 60
    rate_limit_search_per_minute: int = 30
    rate_limit_chat_per_minute: int = 20
    rate_limit_agent_run_per_hour: int = 20

    # --- Embeddings (Phase 5) ---
    # Dimension is a hard constraint, not a preference: pgvector columns have
    # a fixed size, so changing to a model with a different output dimension
    # requires a new migration and re-embedding existing chunks — see
    # docs/adr and app/models/document_chunk.py.
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384

    # --- Chunking (Phase 5) ---
    # Character-based, not token-based: a real tokenizer (e.g. tiktoken)
    # needs to download its encoding tables from a host this environment's
    # egress proxy blocks (see ADR-008's note on huggingface.co for the same
    # class of constraint). ~4 chars/token is a common rough estimate, so
    # these defaults approximate ~250 tokens per chunk with ~40 token overlap.
    chunk_size_chars: int = 1000
    chunk_overlap_chars: int = 150

    # --- Hybrid search (Phase 6) ---
    # HybridScore = alpha * semantic_score + beta * lexical_score, applied
    # after min-max normalizing each signal within the retrieved candidate
    # pool (the two raw scores — cosine similarity, ts_rank — are on
    # different scales and not directly comparable without this).
    hybrid_search_alpha: float = 0.5
    hybrid_search_beta: float = 0.5
    # How many candidates each of semantic/keyword search retrieves before
    # fusion (and reranking, if enabled) narrows down to the final top_k.
    search_candidate_pool_size: int = 20
    search_default_top_k: int = 10
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # --- Auth (wired up in Phase 3) ---
    jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14

    @model_validator(mode="after")
    def _refuse_insecure_secret_in_production(self) -> "Settings":
        """A real, meaningful safety net (ADR-020), not just documentation:
        this app would otherwise happily start — and issue validly-signed
        auth tokens — with a publicly-known default secret in production.
        Only fires for environment == "production": development and test
        both legitimately use known, shared secrets on purpose.
        """
        insecure_default = "dev-only-insecure-secret-change-me"
        if self.environment == "production" and self.jwt_secret == insecure_default:
            raise ValueError(
                "Refusing to start with the default JWT_SECRET while "
                "ENVIRONMENT=production. Generate a real secret "
                "(e.g. `openssl rand -hex 32`) and set it in your environment."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor — read once per process, injected via FastAPI Depends."""
    return Settings()
