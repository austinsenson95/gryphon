"""Application configuration via pydantic-settings.

Reads environment variables (and a local `.env` file if present). Boot must
never require external credentials: every integration falls back to a local
mock when its settings are absent.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "0.1.0"

def _resolve_env_file() -> Path:
    """Resolve credentials outside packaged code when desktop supplies a path."""
    configured = os.environ.get("GRIFFIN_CONFIG_FILE", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    # Project root is two directories above this file (backend/core/config.py).
    return Path(__file__).resolve().parents[2] / "config" / ".env"


_ENV_FILE = _resolve_env_file()


class Settings(BaseSettings):
    """Griffin backend settings. Env var names are contractual."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core
    app_name: str = "Griffin"
    environment: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    griffin_runtime_mode: str = "browser"
    griffin_log_level: str = "INFO"

    # LLM
    llm_provider: str = "ollama"  # "ollama" | "xai" | "openai_compatible" (mock fallback)
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""

    # Ollama (local model runtime)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""
    ollama_timeout: float = 60.0

    # xAI (Grok) provider
    xai_api_key: str = ""
    xai_base_url: str = "https://api.x.ai/v1"
    xai_model: str = "grok-4.5"

    # Speech-to-text
    stt_provider: str = "local"  # "local" | "disabled"
    stt_model: str = "base"  # faster-whisper model size or whisper.cpp model name
    whisper_cpp_bin: str = ""  # path to whisper.cpp CLI (e.g. whisper-cli)
    whisper_cpp_model_path: str = ""  # path to ggml-*.bin model file

    # Optional external tools
    search_api_key: str = ""
    search_api_url: str = ""
    browser_headless: bool = False

    # Browser automation (Phase 1 — Griffin-controlled browser)
    browser_goto_timeout_ms: int = 15_000
    browser_profile_dir: str = "~/.griffin/browser-profile"
    browser_screenshot_dir: str = "~/.griffin/browser-screenshots"

    # Agent loop rails (Phase 1)
    agent_max_steps: int = 4  # max LLM/tool iterations per run (prevents loops)
    max_tool_retries: int = 2  # bounded retries for transient tool failures (timeouts)
    tool_timeout: float = 30.0  # seconds before a tool call is aborted

    # Desktop execution safety rails (Phase 1)
    default_browser: str = ""  # e.g. "Safari"; empty = system default browser
    allowed_applications: str = (
        "Safari,Google Chrome,Firefox,Arc,Visual Studio Code,Terminal,"
        "iTerm,Notes,Calendar,Finder,Slack,Spotify"
    )
    allowed_directories: str = "~/Projects,~/Documents,~/Desktop,~/Downloads"
    projects: str = ""  # JSON object: {"griffin": "~/Projects/griffin", ...}
    search_engine_url: str = "https://www.google.com/search?q={query}"
    news_sites: str = "https://news.ycombinator.com"
    research_topic: str = "latest AI agent frameworks"

    # Storage / security
    database_url: str = "sqlite:///./griffin.db"
    griffin_dev_token: str = ""

    # CORS
    frontend_origin: str = "http://localhost:5173"

    @property
    def async_database_url(self) -> str:
        """Translate the configured DATABASE_URL into an async driver URL.

        `sqlite:///./griffin.db` -> `sqlite+aiosqlite:///./griffin.db`.
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
        """Explicit browser, Vite, and bundled Tauri dashboard origins."""
        origins = {
            self.frontend_origin,
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://tauri.localhost",
            "tauri://localhost",
            "tauri://localhost:5173",
        }
        return sorted(origins)

    @property
    def llm_mode(self) -> str:
        """'live' when a real model endpoint is configured (Ollama, xAI, or
        OpenAI-compatible), 'mock' otherwise."""
        if self.llm_provider == "ollama" and self.ollama_model:
            return "live"
        if self.llm_provider == "xai" and self.xai_api_key:
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
