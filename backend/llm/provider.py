"""LLM provider selection.

``get_llm_provider(settings)`` returns an OpenAI-compatible provider when
``LLM_PROVIDER=openai_compatible`` AND ``LLM_API_KEY`` is set; otherwise the
deterministic, network-free :class:`MockLLMProvider`. The mock is the
sanctioned offline fallback (SPEC §2): it is rule-based, but the tool calls it
emits are REAL — the agent executes them through the tool registry.
"""

from __future__ import annotations

import json
import re
import uuid

from backend.core.config import Settings
from backend.core.logging import get_logger
from backend.llm.base import LLMMessage, LLMProvider, LLMResponse, LLMToolCall

logger = get_logger("gryphon.llm")

_OPEN_URL_RE = re.compile(r"open\s+(https?://\S+)", re.IGNORECASE)
_SEARCH_RE = re.compile(r"search(?:\s+for)?\s+(.+)", re.IGNORECASE | re.DOTALL)

_MOCK_IDENTITY = (
    "I'm Gryphon, a local-first personal AI assistant (running in mock mode — "
    "no LLM API key configured). I can tell you the time, search the web, and "
    "open URLs in a browser. Try: \"What time is it?\", \"search for local "
    "news\", or \"open https://example.com\"."
)


def _tool_call(name: str, arguments: dict) -> LLMToolCall:
    return LLMToolCall(id=f"call_{uuid.uuid4().hex[:12]}", name=name, arguments=arguments)


class MockLLMProvider(LLMProvider):
    """Deterministic rule-based provider used when no credentials exist.

    Rules (first match wins, evaluated against the latest user message):
      * contains "time"                     -> system.get_time {}
      * matches /open\\s+(https?://\\S+)/i   -> browser.open_url {"url": ...}
      * contains "search" + `search[ for] <q>` -> web.search {"query": q}
      * otherwise                           -> conversational content reply

    When the latest message is a tool result, it synthesizes a natural-language
    sentence from the tool data so the agent can finish the turn.
    """

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[dict] | None = None,
        **kw,
    ) -> LLMResponse:
        if not messages:
            return LLMResponse(content=_MOCK_IDENTITY)

        last = messages[-1]
        if last.role == "tool":
            return LLMResponse(content=self._synthesize_tool_answer(messages))

        user_text = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )
        lowered = user_text.lower()

        if "time" in lowered:
            return LLMResponse(tool_calls=[_tool_call("system.get_time", {})])

        match = _OPEN_URL_RE.search(user_text)
        if match:
            return LLMResponse(
                tool_calls=[_tool_call("browser.open_url", {"url": match.group(1)})]
            )

        if "search" in lowered:
            match = _SEARCH_RE.search(user_text)
            if match:
                query = match.group(1).strip().rstrip("?.!")
                if query:
                    return LLMResponse(
                        tool_calls=[_tool_call("web.search", {"query": query})]
                    )

        return LLMResponse(content=_MOCK_IDENTITY)

    def _synthesize_tool_answer(self, messages: list[LLMMessage]) -> str:
        """Build a final natural-language answer from tool result messages."""
        tool_msgs = [m for m in messages if m.role == "tool"]
        if not tool_msgs:
            return "Done."
        parts: list[str] = []
        for msg in tool_msgs:
            try:
                result = json.loads(msg.content)
            except (json.JSONDecodeError, TypeError):
                parts.append(f"Tool {msg.name or 'unknown'} finished.")
                continue
            parts.append(self._describe_tool_result(msg.name or result.get("tool", "unknown"), result))
        return " ".join(parts)

    @staticmethod
    def _describe_tool_result(name: str, result: dict) -> str:
        if not result.get("success"):
            error = (result.get("error") or {}).get("message", "unknown error")
            return f"I tried to run {name}, but it failed: {error}"
        data = result.get("data") or {}
        if name == "system.get_time":
            return (
                f"The current time is {data.get('human', data.get('iso', 'unknown'))} "
                f"({data.get('timezone', 'local timezone')})."
            )
        if name == "system.get_info":
            return (
                f"This is {data.get('app', 'Gryphon')} v{data.get('version', '?')} "
                f"running on {data.get('platform', 'this machine')} "
                f"(Python {data.get('python_version', '?')}, host {data.get('hostname', '?')})."
            )
        if name == "web.search":
            results = data.get("results", [])
            lines = [f"I searched for \"{data.get('query', '')}\". Top results:"]
            for idx, item in enumerate(results[:3], start=1):
                lines.append(f"{idx}. {item.get('title', '?')} — {item.get('url', '')}")
            if data.get("mock"):
                lines.append("(mock results — no search API configured)")
            return "\n".join(lines)
        if name == "browser.open_url":
            if data.get("opened"):
                return f"I opened {data.get('url')} — page title: \"{data.get('title', '')}\"."
            return (
                f"I couldn't fully open {data.get('url')}: "
                f"{data.get('note', 'browser unavailable')}."
            )
        return f"Tool {name} returned: {json.dumps(data, default=str)}"


class OpenAICompatibleProvider(LLMProvider):
    """Live provider using the ``openai`` SDK against any compatible endpoint."""

    def __init__(self, settings: Settings) -> None:
        from openai import AsyncOpenAI  # imported lazily; only needed in live mode

        kwargs: dict = {"api_key": settings.llm_api_key}
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
        self._client = AsyncOpenAI(**kwargs)
        self._model = settings.llm_model or "gpt-4o-mini"

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[dict] | None = None,
        **kw,
    ) -> LLMResponse:
        request: dict = {
            "model": self._model,
            "messages": [self._to_openai_message(m) for m in messages],
        }
        if tools:
            request["tools"] = tools
        completion = await self._client.chat.completions.create(**request)
        choice = completion.choices[0].message
        tool_calls = [
            LLMToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=json.loads(tc.function.arguments or "{}"),
            )
            for tc in (choice.tool_calls or [])
        ]
        return LLMResponse(content=choice.content, tool_calls=tool_calls)

    @staticmethod
    def _to_openai_message(msg: LLMMessage) -> dict:
        # History tool messages are flattened to text so a transcript replayed
        # from the DB stays valid even without the original assistant tool_calls.
        if msg.role == "tool" and msg.tool_call_id:
            return {
                "role": "tool",
                "tool_call_id": msg.tool_call_id,
                "content": msg.content,
            }
        if msg.role == "tool":
            return {"role": "user", "content": f"[tool {msg.name}] {msg.content}"}
        return {"role": msg.role, "content": msg.content}


def get_llm_provider(settings: Settings) -> LLMProvider:
    """Factory: live OpenAI-compatible provider when configured, else mock."""
    if settings.llm_provider == "openai_compatible" and settings.llm_api_key:
        logger.info("llm.provider_selected", extra={"provider": "openai_compatible", "mode": "live"})
        return OpenAICompatibleProvider(settings)
    logger.info("llm.provider_selected", extra={"provider": "mock", "mode": "mock"})
    return MockLLMProvider()
