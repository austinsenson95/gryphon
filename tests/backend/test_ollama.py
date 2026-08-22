"""Ollama provider tests: response parsing, fail-closed behavior, health."""

from __future__ import annotations

import json

import httpx
import pytest

from backend.core.config import Settings
from backend.llm.base import LLMMessage
from backend.llm.ollama import OllamaProvider, OllamaUnavailableError


class _FakeResponse:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=None, response=None)

    def json(self):
        return self._payload


class _FakeClient:
    """Scripted stand-in for httpx.AsyncClient."""

    def __init__(self, routes: dict, calls: list):
        self._routes = routes
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kw):
        self._calls.append(("GET", url))
        route = self._routes[url]
        if isinstance(route, Exception):
            raise route
        return route

    async def post(self, url, json=None, **kw):
        self._calls.append(("POST", url, json))
        route = self._routes[url]
        if isinstance(route, Exception):
            raise route
        if callable(route):
            return route(json)
        return route


def _settings() -> Settings:
    return Settings(
        ollama_base_url="http://localhost:11434",
        ollama_model="test-model",
        _env_file=None,
    )


@pytest.fixture
def client_calls():
    return []


def _patch(monkeypatch, routes, calls):
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: _FakeClient(routes, calls)
    )


async def test_generate_parses_tool_calls(monkeypatch, client_calls):
    def chat(payload):
        return _FakeResponse(
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "desktop.open_url",
                                "arguments": {"url": "https://github.com"},
                            }
                        }
                    ],
                }
            }
        )

    _patch(monkeypatch, {"http://localhost:11434/api/chat": chat}, client_calls)
    provider = OllamaProvider(_settings())
    response = await provider.generate(
        [LLMMessage(role="user", content="Open GitHub")],
        tools=[{"type": "function", "function": {"name": "desktop.open_url"}}],
    )
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "desktop.open_url"
    assert response.tool_calls[0].arguments == {"url": "https://github.com"}
    # Tools were forwarded to Ollama
    assert client_calls[0][2]["tools"]


async def test_generate_drops_malformed_tool_arguments(monkeypatch, client_calls):
    def chat(payload):
        return _FakeResponse(
            {
                "message": {
                    "role": "assistant",
                    "content": "ok",
                    "tool_calls": [
                        {"function": {"name": "desktop.open_url", "arguments": "rm -rf /"}}
                    ],
                }
            }
        )

    _patch(monkeypatch, {"http://localhost:11434/api/chat": chat}, client_calls)
    provider = OllamaProvider(_settings())
    response = await provider.generate([LLMMessage(role="user", content="hi")])
    # Untrusted malformed arguments fail closed — the call is dropped.
    assert response.tool_calls == []
    assert response.content == "ok"


async def test_generate_raises_structured_error_when_down(monkeypatch, client_calls):
    _patch(
        monkeypatch,
        {"http://localhost:11434/api/chat": httpx.ConnectError("refused")},
        client_calls,
    )
    provider = OllamaProvider(_settings())
    with pytest.raises(OllamaUnavailableError):
        await provider.generate([LLMMessage(role="user", content="hi")])


async def test_health_check_reports_missing_model(monkeypatch, client_calls):
    _patch(
        monkeypatch,
        {"http://localhost:11434/api/tags": _FakeResponse({"models": [{"name": "other:latest"}]})},
        client_calls,
    )
    provider = OllamaProvider(_settings())
    health = await provider.health_check()
    assert health["reachable"] is True
    assert health["model_available"] is False
    assert "test-model" in health["error"]


async def test_health_check_full_success(monkeypatch, client_calls):
    def chat(payload):
        return _FakeResponse({"message": {"role": "assistant", "content": "ok"}})

    _patch(
        monkeypatch,
        {
            "http://localhost:11434/api/tags": _FakeResponse(
                {"models": [{"name": "test-model:latest"}]}
            ),
            "http://localhost:11434/api/chat": chat,
        },
        client_calls,
    )
    provider = OllamaProvider(_settings())
    health = await provider.health_check()
    assert health["reachable"] and health["model_available"] and health["inference_ok"]
    assert health["error"] is None


async def test_health_check_unreachable(monkeypatch, client_calls):
    _patch(
        monkeypatch,
        {"http://localhost:11434/api/tags": httpx.ConnectError("refused")},
        client_calls,
    )
    provider = OllamaProvider(_settings())
    health = await provider.health_check()
    assert health["reachable"] is False
    assert health["error"]
