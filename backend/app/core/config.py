from __future__ import annotations

from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict



class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Supabase ────────────────────────────────────────────────
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_anon_key: str = ""

    # ── Embeddings ──────────────────────────────────────────────
    voyage_api_key: str = ""
    openai_api_key: str = ""
    embedding_dimension: int = 1024  # 1024 for Voyage, 1536 for OpenAI

    # ── Groq (LLM for answer generation) ──────────────────────
    groq_api_key: str = ""
    # No model name is hardcoded: set GROQ_MODEL (check console.groq.com/docs/models)
    groq_model: str = ""
    llm_max_retries: int = 3  # retries on rate limit / transient errors, with backoff

    # ── LLM provider switch ─────────────────────────────────────
    llm_provider: str = "groq"  # "groq" (default) or "anthropic" (optional path)
    anthropic_api_key: str = ""
    anthropic_model: str = ""  # only used when LLM_PROVIDER=anthropic

    # ── Ingestion ───────────────────────────────────────────────
    # "llamaindex" (default; falls back to legacy automatically on any error) or "legacy"
    ingestion_pipeline: str = "llamaindex"

    # ── Rate Limiting & Caching (Redis optional) ────────────────
    query_rate_limit: str = "10/minute"
    max_retrieved_chunks: int = 5
    similarity_threshold: float = 0.3
    redis_url: str = ""  # if unset, caching + Redis rate limiting are disabled
    cache_ttl_seconds: int = 3600

    # ── App Config ──────────────────────────────────────────────
    environment: str = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"

    # ── MCP Server (optional, separate entry point) ─────────────
    mcp_org_id: str = ""

    # ── File Storage (optional S3; default "supabase" as today) ─
    storage_backend: str = "supabase"  # "supabase" (default) or "s3"
    s3_bucket_name: str = ""
    aws_region: str = ""

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    @property
    def use_voyage(self) -> bool:
        return bool(self.voyage_api_key)

    @property
    def use_openai(self) -> bool:
        return bool(self.openai_api_key) and not self.use_voyage


# Singleton — import this everywhere
settings = Settings()
