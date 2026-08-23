"""Planner: builds the LLM conversation (system prompt + history) and selects
the tool schemas offered to the model for a given turn.

The system prompt lives in ``prompts/agent_system.txt`` and the command
catalog section is injected dynamically from the tool registry, so registered
tools and workflows are never duplicated by hand.
"""

from __future__ import annotations

from pathlib import Path

from backend.memory.models import Message
from backend.llm.base import LLMMessage
from backend.tools.registry import ToolRegistry

HISTORY_LIMIT = 20

_PROMPT_FILE = Path(__file__).resolve().parents[2] / "prompts" / "agent_system.txt"

_FALLBACK_PROMPT = (
    "You are Griffin, a local-first personal AI assistant. You may only act by "
    "calling registered tools; never output executable code. Available tools:\n"
    "{command_catalog}"
)


def _load_prompt_template() -> str:
    try:
        return _PROMPT_FILE.read_text(encoding="utf-8")
    except OSError:
        return _FALLBACK_PROMPT


def _command_catalog(registry: ToolRegistry) -> str:
    lines = []
    for tool in registry.list():
        if tool.permission == "privileged":
            continue  # never advertised to the model
        lines.append(f"- {tool.name}: {tool.description}")
    return "\n".join(lines)


def system_prompt(registry: ToolRegistry) -> str:
    return _load_prompt_template().replace(
        "{command_catalog}", _command_catalog(registry)
    )


def build_messages(
    history: list[Message], registry: ToolRegistry
) -> list[LLMMessage]:
    """System prompt + persisted history converted to LLM messages."""
    messages = [LLMMessage(role="system", content=system_prompt(registry))]
    for row in history:
        role = row.role if row.role in ("user", "assistant", "tool", "system") else "user"
        messages.append(
            LLMMessage(role=role, content=row.content, name=row.tool_name)
        )
    return messages


def select_tools(registry: ToolRegistry) -> list[dict]:
    """Tool schemas offered to the LLM (privileged tools are never exposed)."""
    return registry.openai_schemas()
