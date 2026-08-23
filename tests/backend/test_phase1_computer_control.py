"""Phase 1 — Computer Control: new coverage for the mission.

Covers (spec §22): browser + desktop tool registration, risk levels,
permission events, run_id propagation, multi-step agent iteration, executor
bounded retries, voice run_id, the /api/browser status endpoint, and a real
headless browser round-trip against a local test page.
"""

from __future__ import annotations

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from backend.core import executor
from backend.core.agent import Agent
from backend.core.permissions import HIGH, LOW, MEDIUM, risk_level
from backend.events.events import EventType
from backend.llm.base import LLMMessage, LLMResponse, LLMToolCall
from backend.llm.provider import MockLLMProvider
from backend.services.message_service import MessageService
from backend.tools.registry import ToolRegistry, create_default_registry
from backend.tools.schemas import Tool, ToolResult


def _playwright_available() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except Exception:
        return False


# ------------------------------------------------------------------ registry


def test_browser_tools_registered(registry):
    names = {t.name for t in registry.list()}
    for expected in [
        "browser.open", "browser.back", "browser.forward", "browser.refresh",
        "browser.inspect", "browser.click", "browser.type", "browser.scroll",
        "browser.extract", "browser.screenshot", "browser.wait",
        "browser.open_url",  # backward-compat alias
    ]:
        assert expected in names, f"missing {expected}"
    exposed = {s["function"]["name"] for s in registry.openai_schemas()}
    assert "browser.open" in exposed
    assert "browser.inspect" in exposed
    assert "browser.click" in exposed
    assert "browser.type" in exposed
    # Browser tools carry an explicit category.
    assert registry.get("browser.open").category == "browser"


def test_desktop_tools_registered(registry):
    names = {t.name for t in registry.list()}
    for expected in [
        "desktop.open_app", "desktop.open_url", "desktop.close_app",
        "desktop.notification", "desktop.clipboard_read", "desktop.clipboard_write",
        "desktop.open_application",
    ]:
        assert expected in names, f"missing {expected}"
    # Clipboard write is MEDIUM risk (confirm); read is LOW risk (safe).
    assert registry.get("desktop.clipboard_write").permission == "confirm"
    assert registry.get("desktop.clipboard_read").permission == "safe"


async def test_health_lists_categories(client):
    body = (await client.get("/api/health/tools")).json()
    by_name = {t["name"]: t for t in body["tools"]}
    assert by_name["browser.open"]["category"] == "browser"
    assert by_name["desktop.open_url"]["category"] == "desktop"
    assert by_name["system.get_time"]["category"] == "system"
    assert by_name["web.search"]["category"] == "web"


# ------------------------------------------------------------------ permissions


def test_risk_levels_map_to_permissions():
    assert risk_level("safe") == LOW
    assert risk_level("confirm") == MEDIUM
    assert risk_level("privileged") == HIGH


async def test_agent_emits_permission_events(db, bus, settings):
    """MEDIUM-risk tools emit permission.required + permission.granted;
    HIGH-risk tools emit permission.denied."""
    events = []
    bus.subscribe(events.append)

    async def medium_handler() -> dict:
        return {"done": True}

    async def high_handler() -> dict:
        return {"done": True}

    registry = ToolRegistry()
    registry.register(
        Tool(
            name="medium.action", description="m", input_schema={"type": "object", "properties": {}, "required": []},
            permission="confirm", handler=medium_handler,
        )
    )
    registry.register(
        Tool(
            name="high.action", description="h", input_schema={"type": "object", "properties": {}, "required": []},
            permission="privileged", handler=high_handler,
        )
    )

    class Provider:
        def __init__(self):
            self.calls = 0

        async def generate(self, messages, tools=None, **kw):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(tool_calls=[LLMToolCall(id="c1", name="medium.action", arguments={})])
            if self.calls == 2:
                return LLMResponse(tool_calls=[LLMToolCall(id="c2", name="high.action", arguments={})])
            return LLMResponse(content="done.")

    agent = Agent(db=db, bus=bus, registry=registry, provider=Provider(), settings=settings)
    session = await MessageService(db.session_factory).create_session(title="t")
    result = await agent.run(session.id, "run both")

    types = [e.type for e in events]
    assert EventType.PERMISSION_REQUIRED in types
    assert EventType.PERMISSION_GRANTED in types
    assert EventType.PERMISSION_DENIED in types
    assert EventType.USER_APPROVAL_REQUIRED in types  # kept for compatibility
    required = next(e for e in events if e.type == EventType.PERMISSION_REQUIRED)
    assert required.data["tool"] == "medium.action"
    denied = next(e for e in events if e.type == EventType.PERMISSION_DENIED)
    assert denied.data["tool"] == "high.action"
    # The HIGH-risk tool was refused and never executed.
    high_call = next(tc for tc in result.tool_calls if tc["tool"] == "high.action")
    assert high_call["success"] is False
    assert high_call["error"]["code"] == "PERMISSION_DENIED"


# ------------------------------------------------------------------ run_id


async def test_all_events_share_the_same_run_id(db, bus, registry, settings):
    events = []
    bus.subscribe(events.append)
    agent = Agent(db=db, bus=bus, registry=registry, provider=MockLLMProvider(), settings=settings)
    session = await MessageService(db.session_factory).create_session(title="t")

    result = await agent.run(session.id, "What time is it?")

    assert result.run_id.startswith("run_")
    run_ids = {e.run_id for e in events}
    assert len(run_ids) == 1
    assert run_ids == {result.run_id}
    # Tool lifecycle events ride the same run id.
    tool_events = [
        e for e in events
        if e.type in (EventType.TOOL_CALL_STARTED, EventType.TOOL_CALL_COMPLETED)
    ]
    assert tool_events and all(e.run_id == result.run_id for e in tool_events)


async def test_chat_response_carries_run_id(client, app):
    events = []
    app.state.gryphon.bus.subscribe(events.append)
    response = await client.post("/api/chat", json={"message": "What time is it?"})
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"].startswith("run_")
    # SESSION_CREATED is a session-level event published before the run begins
    # and correctly carries no run_id; every event belonging to the request
    # (i.e. with a run_id) must share the response's run_id.
    run_scoped = [e for e in events if e.run_id is not None]
    assert run_scoped, "expected run-scoped events"
    run_ids = {e.run_id for e in run_scoped}
    assert run_ids == {body["run_id"]}


# ------------------------------------------------------------------ agent loop


async def test_agent_iterates_on_tool_results(db, bus, registry, settings):
    """OBSERVE → DECIDE → ACT: the agent chains tool calls, feeding each
    result back to the model until it stops asking for tools."""
    events = []
    bus.subscribe(events.append)

    class MultiStepProvider:
        def __init__(self):
            self.calls = 0

        async def generate(self, messages, tools=None, **kw):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(tool_calls=[LLMToolCall(id="c1", name="system.get_time", arguments={})])
            if self.calls == 2:
                return LLMResponse(tool_calls=[LLMToolCall(id="c2", name="system.get_info", arguments={})])
            return LLMResponse(content="Done after two steps.")

    provider = MultiStepProvider()
    agent = Agent(db=db, bus=bus, registry=registry, provider=provider, settings=settings)
    session = await MessageService(db.session_factory).create_session(title="t")

    result = await agent.run(session.id, "do a multi-step thing")

    assert provider.calls == 3  # 2 tool turns + 1 final
    assert [tc["tool"] for tc in result.tool_calls] == ["system.get_time", "system.get_info"]
    assert result.response == "Done after two steps."
    assert len({e.run_id for e in events}) == 1


async def test_executor_bounded_retry_on_timeout():
    registry = ToolRegistry()
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            await asyncio.sleep(5)
        return {"ok": True}

    registry.register(
        Tool(
            name="x.flaky", description="f",
            input_schema={"type": "object", "properties": {}, "required": []},
            permission="safe", handler=flaky,
        )
    )
    result = await executor.execute_tool(registry, "x.flaky", {}, timeout=0.1, max_retries=1)
    assert result.success is True
    assert calls["n"] == 2  # first attempt timed out, second succeeded


async def test_executor_does_not_retry_deterministic_failure():
    registry = ToolRegistry()
    calls = {"n": 0}

    async def failing():
        calls["n"] += 1
        return ToolResult.fail("x.fail", "INVALID_URL", "bad url")

    registry.register(
        Tool(
            name="x.fail", description="f",
            input_schema={"type": "object", "properties": {}, "required": []},
            permission="safe", handler=failing,
        )
    )
    result = await executor.execute_tool(registry, "x.fail", {}, timeout=1.0, max_retries=3)
    assert result.error.code == "INVALID_URL"
    assert calls["n"] == 1  # never retried


# ------------------------------------------------------------------ voice


async def test_voice_run_id_and_events(client, app, monkeypatch):
    from tests.backend.test_voice_health import FakeSTT
    from backend.tools import desktop

    app.state.gryphon.stt = FakeSTT("Open GitHub")
    events = []
    app.state.gryphon.bus.subscribe(events.append)

    async def _fake(args):
        return True, ""

    monkeypatch.setattr(desktop, "_run_mac_open", _fake)
    monkeypatch.setattr(desktop.shutil, "which", lambda name: None)

    response = await client.post(
        "/api/voice", content=b"\x00fake-audio", headers={"Content-Type": "audio/wav"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"].startswith("run_")
    run_ids = {e.run_id for e in events}
    assert body["run_id"] in run_ids
    assert EventType.TOOL_CALL_COMPLETED in [e.type for e in events]


# ------------------------------------------------------------------ browser status


async def test_browser_status_endpoint(client):
    response = await client.get("/api/browser")
    assert response.status_code == 200
    body = response.json()
    assert set(body) >= {"active", "mock", "url", "title"}
    assert body["active"] is False  # not launched yet in this test


# ------------------------------------------------------------------ mock planner


async def test_mock_provider_compound_plan():
    provider = MockLLMProvider()
    res = await provider.generate(
        [LLMMessage(role="user", content="Open Safari and go to github.com")]
    )
    names = [tc.name for tc in res.tool_calls]
    assert names == ["desktop.open_application", "browser.open"]
    assert res.tool_calls[1].arguments == {"url": "https://github.com"}


# ------------------------------------------------------------------ real browser


@pytest.mark.skipif(not _playwright_available(), reason="playwright not installed")
async def test_real_browser_open_inspect_click_type(tmp_path):
    """A genuine headless browser round-trip against a local test page:
    open → inspect → click → type, with browser navigation events."""
    from backend.core import context as run_context
    from backend.core.config import Settings

    html = (
        "<!doctype html><html><head><title>Griffin Test Page</title></head><body>"
        "<h1>Griffin Test Page</h1>"
        "<a href='/page2'>Next page</a>"
        "<button id='btn'>Click Me</button>"
        "<input id='q' placeholder='Search query' />"
        "</body></html>"
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = b"<h1>Page Two</h1>" if self.path == "/page2" else html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # silence
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    settings = Settings(
        browser_headless=True,
        browser_profile_dir=str(tmp_path / "profile"),
        browser_screenshot_dir=str(tmp_path / "shots"),
        _env_file=None,
    )
    registry = create_default_registry(settings)
    manager = registry.browser

    class RecordingBus:
        def __init__(self):
            self.events = []

        async def publish(self, event):
            self.events.append(event)

    recording = RecordingBus()
    manager.bind_bus(recording)
    run_context.set_run_id("run_test_browser")

    try:
        opened = await executor.execute_tool(
            registry, "browser.open", {"url": f"http://127.0.0.1:{port}/"}
        )
        assert opened.success, opened
        assert opened.data["title"] == "Griffin Test Page"
        assert opened.data["mock"] is False

        browser_events = [e.type for e in recording.events]
        assert EventType.BROWSER_NAVIGATION in browser_events
        assert EventType.BROWSER_PAGE_LOADED in browser_events
        assert all(e.run_id == "run_test_browser" for e in recording.events)

        inspected = await executor.execute_tool(registry, "browser.inspect", {})
        assert inspected.success, inspected
        elements = inspected.data["elements"]
        assert elements, "expected interactive elements on the test page"

        button = next(e for e in elements if e["name"] == "Click Me")
        clicked = await executor.execute_tool(
            registry, "browser.click", {"element": str(button["index"])}
        )
        assert clicked.success, clicked

        field = next(e for e in elements if "Search query" in (e["name"] or ""))
        typed = await executor.execute_tool(
            registry,
            "browser.type",
            {"element": str(field["index"]), "text": "hello", "submit": True},
        )
        assert typed.success, typed
    finally:
        run_context.set_run_id(None)
        await manager.close()
        server.shutdown()
        thread.join(timeout=2)
