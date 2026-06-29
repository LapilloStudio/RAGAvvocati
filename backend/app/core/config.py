"""Application settings, loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---- Supabase ----
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    # ---- Anthropic ----
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"
    anthropic_max_tokens: int = 4096
    anthropic_inference_geo: str = ""  # "eu" to pin EU inference (Opus 4.6+)

    # ---- Embeddings ----
    embeddings_provider: str = "managed"  # managed | fake | selfhosted
    embeddings_api_base: str = "https://api.openai.com/v1"
    embeddings_api_key: str = ""
    embeddings_model: str = "text-embedding-3-large"
    embeddings_dimension: int = 1536  # MUST match the vector(N) column

    # ---- App ----
    backend_cors_origins: str = "http://localhost:3000"
    storage_bucket: str = "documents"
    chunk_size: int = 1200
    chunk_overlap: int = 150
    retrieval_top_k: int = 8
    log_level: str = "INFO"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
