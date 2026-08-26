"""Tool registry.

Holds every tool the system knows about. ``openai_schemas()`` exposes only
non-privileged tools to the LLM; privileged tools stay registered (so they are
discoverable/auditable) but are hidden from the model and refuse execution.
"""

from __future__ import annotations

from backend.core.config import Settings
from backend.core.logging import get_logger
from backend.tools import browser, desktop, phone, research, terminal, workflows
from backend.tools.schemas import Tool

logger = get_logger("griffin.tools")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool
        logger.info(
            "tools.registered",
            extra={"tool": tool.name, "permission": tool.permission},
        )

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list(self) -> list[Tool]:
        return list(self._tools.values())

    def category_of(self, tool: Tool) -> str:
        """Effective category: explicit value, else derived from the name prefix."""
        if tool.category != "general":
            return tool.category
        return tool.name.split(".", 1)[0] if "." in tool.name else "general"

    def openai_schemas(self) -> list[dict]:
        """OpenAI tool schemas for LLM-visible (non-privileged) tools only."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in self._tools.values()
            if tool.permission != "privileged"
        ]


def create_default_registry(settings: Settings, bus=None, phone_service=None) -> ToolRegistry:
    """Build the registry with all built-in tools (Phase 0 + Phase 1)."""
    registry = ToolRegistry()
    terminal.register(registry, settings)
    research.register(registry, settings)
    browser.register(registry, settings, bus=bus)
    desktop.register(registry, settings)
    workflows.register(registry, settings, bus=bus)
    if phone_service is not None:
        phone.register(registry, phone_service)
    return registry
