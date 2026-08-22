"""LLM abstraction contract (SPEC §2).

All providers speak these shapes so the agent runtime never cares whether it
is talking to a live OpenAI-compatible endpoint or the deterministic offline
mock.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None
    name: str | None = None


class LLMToolCall(BaseModel):
    id: str
    name: str
    arguments: dict = Field(default_factory=dict)


class LLMResponse(BaseModel):
    content: str | None = None
    tool_calls: list[LLMToolCall] = Field(default_factory=list)


class LLMProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[dict] | None = None,
        **kw,
    ) -> LLMResponse:
        """Generate the next assistant turn (content and/or tool calls)."""
        raise NotImplementedError
