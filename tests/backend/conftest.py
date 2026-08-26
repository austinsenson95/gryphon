"""Shared test fixtures.

Every test gets an isolated app instance backed by a fresh temporary SQLite
database, with the lifespan fully started via asgi-lifespan.
"""

from __future__ import annotations

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from backend.core.config import Settings
from backend.memory.database import Database
from backend.events.bus import EventBus
from backend.events.websocket_manager import WebSocketManager
from backend.llm.provider import MockLLMProvider
from backend.main import create_app
from backend.tools.registry import create_default_registry


@pytest.fixture
def settings(tmp_path, monkeypatch) -> Settings:
    # Isolate tests from any developer .env on disk.
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("SEARCH_API_URL", raising=False)
    for key in (
        "PHONE_AGENT_ENV_FILE",
        "PHONE_WEBHOOK_SECRET",
        "PHONE_PUBLIC_URL",
        "VOBIZ_AUTH_ID",
        "VOBIZ_AUTH_TOKEN",
        "VOBIZ_DID",
        "SARVAM_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    return Settings(
        database_url=f"sqlite:///{tmp_path}/test.db",
        _env_file=None,
    )


@pytest.fixture
async def db(settings) -> Database:
    database = Database(settings.async_database_url)
    await database.create_tables()
    yield database
    await database.dispose()


@pytest.fixture
def registry(settings):
    return create_default_registry(settings)


@pytest.fixture
async def bus(db):
    manager = WebSocketManager()
    return EventBus(db.session_factory, manager)


@pytest.fixture
async def app(settings):
    application = create_app(settings)
    async with LifespanManager(application):
        yield application


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


@pytest.fixture
def mock_provider() -> MockLLMProvider:
    return MockLLMProvider()
