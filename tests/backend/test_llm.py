"""LLM abstraction tests: contract shapes + mock provider rules + factory."""

from backend.core.config import Settings
from backend.llm.base import LLMMessage, LLMProvider, LLMResponse, LLMToolCall
from backend.llm.provider import MockLLMProvider, create_provider, get_llm_provider
from backend.llm.xai import XAIProvider


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
    assert response.tool_calls[0].name == "desktop.open_url"
    assert response.tool_calls[0].arguments == {"url": "https://example.com/docs"}


async def test_mock_search_rule(mock_provider):
    response = await mock_provider.generate(_user("can you search for local news?"))
    assert response.tool_calls[0].name == "desktop.search_web"
    assert response.tool_calls[0].arguments["query"] == "local news"


async def test_mock_youtube_search_stays_site_scoped(mock_provider):
    response = await mock_provider.generate(
        _user("Open YouTube and search for ambient focus music")
    )
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "desktop.search_youtube"
    assert response.tool_calls[0].arguments == {"query": "ambient focus music"}


async def test_mock_youtube_playback_uses_controlled_browser_chain(mock_provider):
    import json

    messages = _user("Open YouTube and play Pink Floyd songs")
    response = await mock_provider.generate(messages)
    assert response.tool_calls[0].name == "browser.open"
    assert "youtube.com/results" in response.tool_calls[0].arguments["url"]

    messages.append(
        LLMMessage(
            role="tool",
            name="browser.open",
            tool_call_id=response.tool_calls[0].id,
            content=json.dumps({"success": True, "data": {"url": response.tool_calls[0].arguments["url"]}}),
        )
    )
    response = await mock_provider.generate(messages)
    assert response.tool_calls[0].name == "browser.inspect"

    messages.append(
        LLMMessage(
            role="tool",
            name="browser.inspect",
            tool_call_id=response.tool_calls[0].id,
            content=json.dumps(
                {
                    "success": True,
                    "data": {
                        "elements": [
                            {"index": 7, "role": "link", "name": "Pink Floyd - Time", "href": "/watch?v=123"}
                        ]
                    },
                }
            ),
        )
    )
    response = await mock_provider.generate(messages)
    assert response.tool_calls[0].name == "browser.click"
    assert response.tool_calls[0].arguments["index"] == 7

    messages.append(
        LLMMessage(
            role="tool",
            name="browser.click",
            tool_call_id=response.tool_calls[0].id,
            content=json.dumps({"success": True, "data": {"url": "https://www.youtube.com/watch?v=123"}}),
        )
    )
    response = await mock_provider.generate(messages)
    assert response.tool_calls[0].name == "browser.inspect"

    messages.append(
        LLMMessage(
            role="tool",
            name="browser.inspect",
            tool_call_id=response.tool_calls[0].id,
            content=json.dumps(
                {
                    "success": True,
                    "data": {
                        "url": "https://www.youtube.com/watch?v=123",
                        "elements": [{"index": 2, "role": "button", "name": "Pause (k)"}],
                    },
                }
            ),
        )
    )
    response = await mock_provider.generate(messages)
    assert response.tool_calls == []
    assert "started playing" in response.content


async def test_mock_spotify_playback_uses_web_player(mock_provider):
    response = await mock_provider.generate(_user("Play Pink Floyd on Spotify"))
    assert response.tool_calls[0].name == "browser.open"
    assert response.tool_calls[0].arguments["url"] == "https://open.spotify.com/search/Pink+Floyd"


async def test_mock_ignores_injected_task_state_when_planning(mock_provider):
    response = await mock_provider.generate(
        _user("Open YouTube and search for ambient focus music")
        + [LLMMessage(role="user", content="CURRENT TASK STATE:\ngoal: internal note")]
    )
    assert response.tool_calls[0].arguments == {"query": "ambient focus music"}


async def test_mock_conversational_fallback_mentions_griffin(mock_provider):
    response = await mock_provider.generate(_user("hello there"))
    assert response.tool_calls == []
    assert response.content
    assert "Griffin" in response.content
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
    settings = Settings(llm_api_key="", xai_api_key="", _env_file=None)
    provider = get_llm_provider(settings)
    assert isinstance(provider, MockLLMProvider)
    assert isinstance(provider, LLMProvider)


def test_create_provider_returns_xai_when_configured():
    settings = Settings(
        llm_provider="xai",
        xai_api_key="xai-test-key",
        xai_model="grok-2-latest",
        _env_file=None,
    )
    provider = create_provider("xai", settings)
    assert isinstance(provider, XAIProvider)


def test_create_provider_xai_without_key_falls_back_to_mock():
    settings = Settings(
        llm_provider="xai",
        xai_api_key="",
        _env_file=None,
    )
    provider = create_provider("xai", settings)
    assert isinstance(provider, MockLLMProvider)


def test_xai_provider_uses_configured_model():
    settings = Settings(
        xai_api_key="xai-test-key",
        xai_model="grok-4.5",
        _env_file=None,
    )
    provider = XAIProvider(settings)
    assert provider._model == "grok-4.5"
