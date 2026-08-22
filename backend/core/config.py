"""Application configuration via pydantic-settings.

Reads environment variables (and a local `.env` file if present). Boot must
never require external credentials: every integration falls back to a local
mock when its settings are absent.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "0.1.0"

# Project root is two directories above this file (backend/core/config.py)
_ENV_FILE = Path(__file__).resolve().parents[2] / "config" / ".env"


class Settings(BaseSettings):
    """Gryphon backend settings. Env var names are contractual."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core
    app_name: str = "Gryphon"
    environment: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000

    # LLM
    llm_provider: str = "openai_compatible"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""

    # Optional external tools
    search_api_key: str = ""
    search_api_url: str = ""
    browser_headless: bool = False

    # Storage / security
    database_url: str = "sqlite:///./gryphon.db"
    gryphon_dev_token: str = ""

    # CORS
    frontend_origin: str = "http://localhost:5173"

    @property
    def async_database_url(self) -> str:
        """Translate the configured DATABASE_URL into an async driver URL.

        `sqlite:///./gryphon.db` -> `sqlite+aiosqlite:///./gryphon.db`.
        Already-async URLs pass through untouched.
        """
        url = self.database_url
        if url.startswith("sqlite:///"):
            return "sqlite+aiosqlite://" + url[len("sqlite://"):]
        if url.startswith("sqlite://") and "+aiosqlite" not in url:
            return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return url

    @property
    def cors_origins(self) -> list[str]:
        """Explicit allowed origins: FRONTEND_ORIGIN + local Vite dev servers."""
        origins = {
            self.frontend_origin,
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        }
        return sorted(origins)

    @property
    def llm_mode(self) -> str:
        """'live' when a real OpenAI-compatible endpoint is configured."""
        if self.llm_provider == "openai_compatible" and self.llm_api_key:
            return "live"
        return "mock"


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor for production wiring."""
    return Settings()
