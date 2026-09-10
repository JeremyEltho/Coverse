"""Application settings, all sourced from the environment.

Everything the app needs to run is declared here so that `.env.example` and the
code can never drift apart.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["mock", "ollama", "openrouter"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    # --- server ---
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    cors_origins: str = "http://localhost:5173"

    # --- AI provider ---
    # `mock` is the default on purpose: the entire product is developable and
    # testable with no API keys and nothing installed locally.
    ai_provider: Provider = "mock"
    ai_model: str = ""
    ai_temperature: float = 0.7
    ai_max_tokens: int = 1024
    ai_request_timeout: float = 120.0

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    mock_delay_ms: int = 25

    # --- database ---
    # Defaults to a local SQLite file so `uvicorn coverse.main:app` works with
    # zero setup. Point at Supabase Postgres for the real thing.
    database_url: str = "sqlite+aiosqlite:///./coverse.db"

    # --- auth (Supabase) ---
    # When no project URL is configured the server runs in dev-auth mode: the
    # token is trusted as an opaque user id. Never enable that in production.
    supabase_url: str = ""
    supabase_jwt_secret: str = ""
    supabase_service_role_key: str = ""
    auth_required: bool = False

    # --- streaming behaviour ---
    # Committing every token as its own CRDT transaction is a write storm, so
    # deltas are batched on this interval (or at a sentence boundary).
    stream_flush_ms: int = 50
    # Debounced persistence of Yjs updates.
    persist_debounce_ms: int = 2000
    persist_max_wait_ms: int = 10000
    # Compact the append-only update log once a document exceeds this many rows.
    compact_after_updates: int = 200

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def resolved_model(self) -> str:
        """The model to use, honouring an explicit AI_MODEL override."""
        if self.ai_model:
            return self.ai_model
        return {
            "openrouter": self.openrouter_model,
            "ollama": self.ollama_model,
            "mock": "mock-model",
        }[self.ai_provider]

    @property
    def is_dev_auth(self) -> bool:
        return not (self.supabase_jwt_secret or self.supabase_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
