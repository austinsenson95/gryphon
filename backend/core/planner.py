"""Planner: builds the LLM conversation (system prompt + history) and selects
the tool schemas offered to the model for a given turn."""

from __future__ import annotations

from backend.memory.models import Message
from backend.llm.base import LLMMessage
from backend.tools.registry import ToolRegistry

SYSTEM_PROMPT = (
    "You are Gryphon, a local-first personal AI assistant. You run entirely on "
    "the user's own machine. You can call tools to answer questions: get the "
    "current time, inspect system info, search the web, and open URLs in a "
    "browser. Be concise, honest, and helpful. When a tool result is available, "
    "summarize it in plain language."
)

HISTORY_LIMIT = 20


def build_messages(history: list[Message]) -> list[LLMMessage]:
    """System prompt + persisted history converted to LLM messages."""
    messages = [LLMMessage(role="system", content=SYSTEM_PROMPT)]
    for row in history:
        role = row.role if row.role in ("user", "assistant", "tool", "system") else "user"
        messages.append(
            LLMMessage(role=role, content=row.content, name=row.tool_name)
        )
    return messages


def select_tools(registry: ToolRegistry) -> list[dict]:
    """Tool schemas offered to the LLM (privileged tools are never exposed)."""
    return registry.openai_schemas()
