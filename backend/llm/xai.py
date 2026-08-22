"""xAI (Grok) LLM provider.

Uses the OpenAI-compatible API at https://api.x.ai/v1. The provider only
proposes structured tool calls; validation and execution happen downstream in
the agent's registry/executor boundary.
"""

from __future__ import annotations

import json

from backend.core.config import Settings
from backend.core.logging import get_logger
from backend.llm.base import LLMMessage, LLMProvider, LLMResponse, LLMToolCall

logger = get_logger("gryphon.llm.xai")


class XAIProvider(LLMProvider):
    """Live provider using the xAI OpenAI-compatible endpoint."""

    def __init__(self, settings: Settings) -> None:
        from openai import AsyncOpenAI  # imported lazily; only needed in live mode

        kwargs: dict = {"api_key": settings.xai_api_key}
        if settings.xai_base_url:
            kwargs["base_url"] = settings.xai_base_url
        self._client = AsyncOpenAI(**kwargs)
        self._model = settings.xai_model or "grok-2-latest"

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
