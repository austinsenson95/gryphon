"""LLM abstraction tests: contract shapes + mock provider rules + factory."""

from backend.llm.base import LLMMessage, LLMProvider, LLMResponse, LLMToolCall
from backend.llm.provider import MockLLMProvider, get_llm_provider


def _user(text: str) -> list[LLMMessage]:
    return [LLMMessage(role="user", content=text)]


async def test_mock_returns_tool_call_for_time_question(mock_provider):
    response = await mock_provider.generate(_user("What time is it?"))
    assert isinstance(response, LLMResponse)
    assert len(response.tool_calls) == 1
    call = response.tool_calls[0]
    assert isinstance(call, LLMToolCall)
    assert call.name == "system.get_time"
    assert call.arguments == {}
    assert call.id


async def test_mock_time_rule_is_case_insensitive(mock_provider):
    response = await mock_provider.generate(_user("TELL ME THE TIME please"))
    assert response.tool_calls[0].name == "system.get_time"


async def test_mock_open_url_rule(mock_provider):
    response = await mock_provider.generate(_user("please open https://example.com/docs"))
    assert response.tool_calls[0].name == "browser.open_url"
    assert response.tool_calls[0].arguments == {"url": "https://example.com/docs"}


async def test_mock_search_rule(mock_provider):
    response = await mock_provider.generate(_user("can you search for local news?"))
    assert response.tool_calls[0].name == "web.search"
    assert response.tool_calls[0].arguments["query"] == "local news"


async def test_mock_conversational_fallback_mentions_gryphon(mock_provider):
    response = await mock_provider.generate(_user("hello there"))
    assert response.tool_calls == []
    assert response.content
    assert "Gryphon" in response.content
    assert "local-first" in response.content
    assert "mock" in response.content.lower()


async def test_mock_synthesizes_answer_from_tool_result(mock_provider):
    import json

    tool_result = {
        "success": True,
        "tool": "system.get_time",
        "data": {"iso": "2025-01-01T12:00:00", "unix": 1, "timezone": "UTC", "human": "noon"},
        "error": None,
    }
    messages = _user("What time is it?") + [
        LLMMessage(role="tool", tool_call_id="call_1", name="system.get_time", content=json.dumps(tool_result))
    ]
    response = await mock_provider.generate(messages)
    assert response.tool_calls == []
    assert "noon" in response.content


def test_provider_factory_falls_back_to_mock():
    from backend.core.config import Settings

    settings = Settings(llm_api_key="", _env_file=None)
    provider = get_llm_provider(settings)
    assert isinstance(provider, MockLLMProvider)
    assert isinstance(provider, LLMProvider)
