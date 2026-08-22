"""Agent runtime tests: conversation, tool invocation, failures, unknown tools."""

from backend.core.agent import Agent
from backend.events.events import EventType
from backend.llm.base import LLMResponse, LLMToolCall
from backend.llm.provider import MockLLMProvider
from backend.services.message_service import MessageService
from backend.services.task_service import TaskService


class ScriptedProvider:
    """Test provider returning a fixed sequence of LLMResponses."""

    def __init__(self, *responses: LLMResponse | Exception):
        self._responses = list(responses)
        self.calls = 0

    async def generate(self, messages, tools=None, **kw) -> LLMResponse:
        self.calls += 1
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


async def _make_agent(db, bus, registry, settings, provider):
    return Agent(db=db, bus=bus, registry=registry, provider=provider, settings=settings)


async def test_agent_normal_conversation_no_tool(db, bus, registry, settings):
    events = []
    bus.subscribe(events.append)
    agent = await _make_agent(db, bus, registry, settings, MockLLMProvider())
    messages = MessageService(db.session_factory)
    session = await messages.create_session(title="t")

    result = await agent.run(session.id, "hello, who are you?")

    assert result.error is None
    assert result.tool_calls == []
    assert "Gryphon" in result.response
    assert result.message_id and result.task_id

    types = [e.type for e in events]
    assert types == [
        EventType.MESSAGE_RECEIVED,
        EventType.TASK_STARTED,
        EventType.AGENT_STARTED,
        EventType.AGENT_THINKING,
        EventType.AGENT_RESPONSE,
        EventType.TASK_COMPLETED,
    ]
    task = await TaskService(db.session_factory).get(result.task_id)
    assert task.status == "completed"
    history = await messages.history(session.id)
    assert [m.role for m in history] == ["user", "assistant"]


async def test_agent_successful_tool_invocation(db, bus, registry, settings):
    events = []
    bus.subscribe(events.append)
    agent = await _make_agent(db, bus, registry, settings, MockLLMProvider())
    session = await MessageService(db.session_factory).create_session(title="t")

    result = await agent.run(session.id, "What time is it?")

    assert result.error is None
    assert len(result.tool_calls) == 1
    record = result.tool_calls[0]
    assert record["tool"] == "system.get_time"
    assert record["success"] is True
    assert "iso" in record["data"]
    assert "time" in result.response.lower()

    types = [e.type for e in events]
    for expected in [
        EventType.MESSAGE_RECEIVED,
        EventType.TASK_STARTED,
        EventType.AGENT_STARTED,
        EventType.AGENT_THINKING,
        EventType.TOOL_CALL_STARTED,
        EventType.TOOL_CALL_COMPLETED,
        EventType.AGENT_RESPONSE,
        EventType.TASK_COMPLETED,
    ]:
        assert expected in types, expected
    assert types.index(EventType.TOOL_CALL_STARTED) < types.index(EventType.TOOL_CALL_COMPLETED)

    tasks = TaskService(db.session_factory)
    task, tool_calls = await tasks.get_with_tool_calls(result.task_id)
    assert task.status == "completed"
    assert len(tool_calls) == 1
    assert tool_calls[0].tool == "system.get_time"
    assert tool_calls[0].success is True


async def test_agent_tool_failure_continues_to_response(db, bus, registry, settings):
    provider = ScriptedProvider(
        LLMResponse(tool_calls=[LLMToolCall(id="c1", name="browser.open_url", arguments={"url": "ftp://bad"})]),
        LLMResponse(content="Sorry, that URL is not valid."),
    )
    events = []
    bus.subscribe(events.append)
    agent = await _make_agent(db, bus, registry, settings, provider)
    session = await MessageService(db.session_factory).create_session(title="t")

    result = await agent.run(session.id, "open ftp://bad")

    assert result.error is None  # tool failure is not an agent failure
    assert result.tool_calls[0]["success"] is False
    assert result.tool_calls[0]["error"]["code"] == "INVALID_URL"
    assert result.response == "Sorry, that URL is not valid."
    types = [e.type for e in events]
    assert EventType.TOOL_CALL_FAILED in types
    assert EventType.TASK_COMPLETED in types


async def test_agent_llm_failure_task_failed_structured(db, bus, registry, settings):
    provider = ScriptedProvider(RuntimeError("llm exploded"))
    events = []
    bus.subscribe(events.append)
    agent = await _make_agent(db, bus, registry, settings, provider)
    session = await MessageService(db.session_factory).create_session(title="t")

    result = await agent.run(session.id, "boom")

    assert result.error == {"code": "AGENT_ERROR", "message": "llm exploded"}
    assert result.response
    assert EventType.TASK_FAILED in [e.type for e in events]
    task = await TaskService(db.session_factory).get(result.task_id)
    assert task.status == "failed"


async def test_agent_unknown_tool(db, bus, registry, settings):
    provider = ScriptedProvider(
        LLMResponse(tool_calls=[LLMToolCall(id="c1", name="nope.missing", arguments={})]),
        LLMResponse(content="I don't have that tool."),
    )
    events = []
    bus.subscribe(events.append)
    agent = await _make_agent(db, bus, registry, settings, provider)
    session = await MessageService(db.session_factory).create_session(title="t")

    result = await agent.run(session.id, "do something weird")

    assert result.tool_calls[0]["success"] is False
    assert result.tool_calls[0]["error"]["code"] == "TOOL_NOT_FOUND"
    assert EventType.TOOL_CALL_FAILED in [e.type for e in events]
    assert result.error is None


async def test_agent_max_iterations_guard(db, bus, registry, settings):
    provider = ScriptedProvider(
        *[LLMResponse(tool_calls=[LLMToolCall(id=f"c{i}", name="system.get_time", arguments={})]) for i in range(6)]
    )
    agent = await _make_agent(db, bus, registry, settings, provider)
    session = await MessageService(db.session_factory).create_session(title="t")

    result = await agent.run(session.id, "loop forever")

    assert provider.calls == 4  # MAX_TOOL_ITERATIONS
    assert "maximum number of tool steps" in result.response
    assert len(result.tool_calls) == 4
