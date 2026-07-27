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
    groq_model: str = "llama-3.3-70b-versatile"

    # ── Rate Limiting ───────────────────────────────────────────
    query_rate_limit: str = "10/minute"
    max_retrieved_chunks: int = 5
    similarity_threshold: float = 0.3

    # ── App Config ──────────────────────────────────────────────
    environment: str = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"

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
