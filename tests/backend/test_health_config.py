"""Health endpoint + config loading tests."""


async def test_health_endpoint(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "gryphon"
    assert body["version"]
    assert body["llm_mode"] in ("live", "mock")


async def test_health_reports_mock_mode_without_credentials(client):
    response = await client.get("/api/health")
    assert response.json()["llm_mode"] == "mock"


def test_config_defaults():
    from backend.core.config import Settings

    settings = Settings(_env_file=None)
    assert settings.app_name == "Gryphon"
    assert settings.environment == "development"
    assert settings.host == "0.0.0.0"
    assert settings.port == 8000
    assert settings.llm_provider == "ollama"
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.stt_provider == "local"
    assert settings.database_url.startswith("sqlite")
    assert settings.frontend_origin == "http://localhost:5173"


def test_config_env_override(monkeypatch):
    from backend.core.config import Settings

    monkeypatch.setenv("APP_NAME", "GryphonTest")
    monkeypatch.setenv("PORT", "9999")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    settings = Settings(_env_file=None)
    assert settings.app_name == "GryphonTest"
    assert settings.port == 9999
    assert settings.llm_mode == "live"


def test_async_database_url_translation():
    from backend.core.config import Settings

    settings = Settings(database_url="sqlite:///./gryphon.db", _env_file=None)
    assert settings.async_database_url == "sqlite+aiosqlite:///./gryphon.db"


def test_cors_origins_include_frontend():
    from backend.core.config import Settings

    settings = Settings(_env_file=None)
    assert "http://localhost:5173" in settings.cors_origins
    assert "http://127.0.0.1:5173" in settings.cors_origins
