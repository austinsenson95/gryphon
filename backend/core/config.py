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
    llm_provider: str = "ollama"  # "ollama" | "openai_compatible" (mock fallback)
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""

    # Ollama (local model runtime)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""
    ollama_timeout: float = 60.0

    # Speech-to-text
    stt_provider: str = "local"  # "local" | "disabled"
    stt_model: str = "base"  # faster-whisper model size or whisper.cpp model name
    whisper_cpp_bin: str = ""  # path to whisper.cpp CLI (e.g. whisper-cli)
    whisper_cpp_model_path: str = ""  # path to ggml-*.bin model file

    # Optional external tools
    search_api_key: str = ""
    search_api_url: str = ""
    browser_headless: bool = False

    # Desktop execution safety rails (Phase 1)
    default_browser: str = ""  # e.g. "Safari"; empty = system default browser
    allowed_applications: str = (
        "Safari,Google Chrome,Firefox,Arc,Visual Studio Code,Terminal,"
        "iTerm,Notes,Calendar,Finder,Slack,Spotify"
    )
    allowed_directories: str = "~/Projects,~/Documents,~/Desktop,~/Downloads"
    projects: str = ""  # JSON object: {"gryphon": "~/Projects/gryphon", ...}
    search_engine_url: str = "https://www.google.com/search?q={query}"
    news_sites: str = "https://news.ycombinator.com"
    research_topic: str = "latest AI agent frameworks"

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
        """'live' when a real model endpoint is configured (Ollama or
        OpenAI-compatible), 'mock' otherwise."""
        if self.llm_provider == "ollama" and self.ollama_model:
            return "live"
        if self.llm_provider == "openai_compatible" and self.llm_api_key:
            return "live"
        return "mock"

    @property
    def allowed_application_list(self) -> list[str]:
        return [a.strip() for a in self.allowed_applications.split(",") if a.strip()]

    @property
    def allowed_directory_paths(self) -> list[Path]:
        return [
            Path(d.strip()).expanduser().resolve()
            for d in self.allowed_directories.split(",")
            if d.strip()
        ]

    @property
    def project_registry(self) -> dict[str, Path]:
        """Named projects from the PROJECTS env JSON object."""
        if not self.projects.strip():
            return {}
        import json

        try:
            raw = json.loads(self.projects)
        except json.JSONDecodeError:
            return {}
        if not isinstance(raw, dict):
            return {}
        return {
            str(name): Path(str(path)).expanduser().resolve()
            for name, path in raw.items()
        }

    @property
    def news_site_list(self) -> list[str]:
        return [u.strip() for u in self.news_sites.split(",") if u.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor for production wiring."""
    return Settings()
