"""Health endpoint + config loading tests."""


async def test_health_endpoint(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "griffin"
    assert body["version"]
    assert body["llm_mode"] in ("live", "mock")


async def test_health_reports_mock_mode_without_credentials(client):
    response = await client.get("/api/health")
    assert response.json()["llm_mode"] == "mock"


def test_config_defaults():
    from backend.core.config import Settings

    settings = Settings(_env_file=None)
    assert settings.app_name == "Griffin"
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

    monkeypatch.setenv("APP_NAME", "GriffinTest")
    monkeypatch.setenv("PORT", "9999")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    settings = Settings(_env_file=None)
    assert settings.app_name == "GriffinTest"
    assert settings.port == 9999
    assert settings.llm_mode == "live"


def test_config_xai_live_mode(monkeypatch):
    from backend.core.config import Settings

    monkeypatch.setenv("LLM_PROVIDER", "xai")
    monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
    settings = Settings(_env_file=None)
    assert settings.llm_mode == "live"


def test_config_xai_without_key_is_mock(monkeypatch):
    from backend.core.config import Settings

    monkeypatch.setenv("LLM_PROVIDER", "xai")
    monkeypatch.setenv("XAI_API_KEY", "")
    settings = Settings(_env_file=None)
    assert settings.llm_mode == "mock"


def test_config_file_env_override(monkeypatch, tmp_path):
    from backend.core.config import _resolve_env_file

    config_file = tmp_path / "griffin.env"
    config_file.write_text("LLM_PROVIDER=xai\n")
    monkeypatch.setenv("GRIFFIN_CONFIG_FILE", str(config_file))
    assert _resolve_env_file() == config_file.resolve()


def test_async_database_url_translation():
    from backend.core.config import Settings

    settings = Settings(database_url="sqlite:///./griffin.db", _env_file=None)
    assert settings.async_database_url == "sqlite+aiosqlite:///./griffin.db"


def test_cors_origins_include_frontend():
    from backend.core.config import Settings

    settings = Settings(_env_file=None)
    assert "http://localhost:5173" in settings.cors_origins
    assert "http://127.0.0.1:5173" in settings.cors_origins
    assert "tauri://localhost" in settings.cors_origins
    assert "tauri://localhost:5173" in settings.cors_origins


async def test_tauri_cors_preflight_is_allowed(client):
    response = await client.options(
        "/api/health",
        headers={
            "Origin": "tauri://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "tauri://localhost:5173"
