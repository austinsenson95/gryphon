"""Voice endpoint + health endpoint tests (Phase 1)."""

from __future__ import annotations

import pytest

from backend.events.events import EventType
from backend.stt.base import STTUnavailableError
from backend.tools import desktop


class FakeSTT:
    def __init__(self, transcript: str | Exception):
        self._transcript = transcript

    async def transcribe(self, audio_path: str, content_type: str = "") -> str:
        if isinstance(self._transcript, Exception):
            raise self._transcript
        return self._transcript

    async def health(self) -> dict:
        return {"provider": "fake", "available": True}


@pytest.fixture
def patched_open(monkeypatch):
    calls: list[list[str]] = []

    async def _fake(args: list[str]):
        calls.append(args)
        return True, ""

    monkeypatch.setattr(desktop, "_run_mac_open", _fake)
    monkeypatch.setattr(desktop.shutil, "which", lambda name: None)
    return calls


async def test_voice_transcribes_and_executes(client, app, patched_open):
    app.state.griffin.stt = FakeSTT("Open GitHub")
    events = []
    app.state.griffin.bus.subscribe(events.append)

    response = await client.post(
        "/api/voice",
        content=b"\x00fake-audio",
        headers={"Content-Type": "audio/wav"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["transcript"] == "Open GitHub"
    assert body["session_id"]
    assert body["error"] is None
    # The transcript drove a real (mocked at OS boundary) execution.
    assert patched_open == [["https://github.com"]]
    types = [e.type for e in events]
    assert EventType.STT_STARTED in types
    assert EventType.STT_COMPLETED in types
    assert EventType.TOOL_CALL_COMPLETED in types


async def test_voice_stt_unavailable(client, app):
    app.state.griffin.stt = FakeSTT(STTUnavailableError("no engine"))
    response = await client.post("/api/voice", content=b"\x00audio")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "STT_UNAVAILABLE"


async def test_voice_empty_body_rejected(client):
    response = await client.post("/api/voice", content=b"")
    assert response.status_code == 422


async def test_health_tools_lists_registry(client):
    response = await client.get("/api/health/tools")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    names = [t["name"] for t in body["tools"]]
    assert "desktop.open_application" in names
    assert "workflow.run" in names
    privileged = [t for t in body["tools"] if t["permission"] == "privileged"]
    assert privileged and all(not t["exposed_to_llm"] for t in privileged)


async def test_health_stt_reports_state(client):
    response = await client.get("/api/health/stt")
    assert response.status_code == 200
    body = response.json()
    assert "available" in body


async def test_health_ollama_without_ollama_provider(client):
    # Default test app boots in mock mode; the endpoint must explain that.
    response = await client.get("/api/health/ollama")
    assert response.status_code == 200
    body = response.json()
    assert body["reachable"] is False
    assert body["error"]
