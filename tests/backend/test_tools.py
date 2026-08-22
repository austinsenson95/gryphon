"""Tool registry, execution, and permission tests."""

from backend.core import executor
from backend.events.events import EventEnvelope, EventType
from backend.tools.schemas import Tool, ToolResult


def test_registry_register_get_list(registry):
    names = [tool.name for tool in registry.list()]
    assert "system.get_time" in names
    assert "system.get_info" in names
    assert "web.search" in names
    assert "browser.open_url" in names
    assert "system.execute_shell" in names  # registered...
    assert registry.get("system.get_time").name == "system.get_time"
    assert registry.get("does.not.exist") is None


def test_openai_schemas_exclude_privileged(registry):
    exposed = {schema["function"]["name"] for schema in registry.openai_schemas()}
    assert "system.get_time" in exposed
    assert "web.search" in exposed
    assert "browser.open_url" in exposed
    assert "system.execute_shell" not in exposed  # ...but never exposed to the LLM
    for schema in registry.openai_schemas():
        assert schema["type"] == "function"
        assert "description" in schema["function"]
        assert "parameters" in schema["function"]


async def test_execute_get_time_returns_real_data(registry):
    result = await executor.execute_tool(registry, "system.get_time", {})
    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.tool == "system.get_time"
    assert set(result.data) >= {"iso", "unix", "timezone", "human"}
    assert isinstance(result.data["unix"], int)


async def test_execute_unknown_tool_structured_error(registry):
    result = await executor.execute_tool(registry, "no.such.tool", {})
    assert result.success is False
    assert result.error.code == "TOOL_NOT_FOUND"


async def test_privileged_tool_refuses_execution(registry):
    result = await executor.execute_tool(registry, "system.execute_shell", {"command": "ls"})
    assert result.success is False
    assert result.error.code == "PERMISSION_DENIED"


async def test_invalid_arguments_structured_error(registry):
    result = await executor.execute_tool(registry, "web.search", {"wrong": "arg"})
    assert result.success is False
    assert result.error.code == "INVALID_ARGUMENTS"


async def test_browser_open_url_validates_scheme(registry):
    result = await executor.execute_tool(registry, "browser.open_url", {"url": "ftp://x"})
    assert result.success is False
    assert result.error.code == "INVALID_URL"


async def test_browser_open_url_mock_fallback(registry):
    # Playwright is not installed in this environment -> sanctioned mock path.
    result = await executor.execute_tool(registry, "browser.open_url", {"url": "https://example.com"})
    assert result.success is True
    assert result.data["mock"] is True
    assert result.data["opened"] is False


async def test_web_search_mock_when_unconfigured(registry):
    result = await executor.execute_tool(registry, "web.search", {"query": "gryphon"})
    assert result.success is True
    assert result.data["mock"] is True
    assert result.data["query"] == "gryphon"
    assert len(result.data["results"]) == 3
    assert all(item["mock"] for item in result.data["results"])


async def test_confirm_tool_emits_approval_event(db, bus, settings):
    """CONFIRM-permission tools emit USER_APPROVAL_REQUIRED (auto-approved in Phase 0)."""
    from backend.core.agent import Agent
    from backend.llm.base import LLMMessage, LLMResponse, LLMToolCall
    from backend.services.message_service import MessageService

    events: list[EventEnvelope] = []
    bus.subscribe(events.append)

    async def dangerous_handler() -> dict:
        return {"done": True}

    from backend.tools.registry import ToolRegistry

    registry = ToolRegistry()
    registry.register(
        Tool(
            name="files.delete",
            description="Delete a file",
            input_schema={"type": "object", "properties": {}, "required": []},
            permission="confirm",
            handler=dangerous_handler,
        )
    )

    class ConfirmProvider:
        def __init__(self):
            self.calls = 0

        async def generate(self, messages, tools=None, **kw):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(tool_calls=[LLMToolCall(id="c1", name="files.delete", arguments={})])
            return LLMResponse(content="File deleted.")

    provider = ConfirmProvider()
    messages = MessageService(db.session_factory)
    session = await messages.create_session(title="t")
    agent = Agent(db=db, bus=bus, registry=registry, provider=provider, settings=settings)
    result = await agent.run(session.id, "delete it")

    types = [e.type for e in events]
    assert EventType.USER_APPROVAL_REQUIRED in types
    approval = next(e for e in events if e.type == EventType.USER_APPROVAL_REQUIRED)
    assert approval.data["tool"] == "files.delete"
    assert approval.data["auto_approved"] is True
    assert result.response == "File deleted."
    assert result.tool_calls[0]["success"] is True
