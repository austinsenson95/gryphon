"""Tool registry.

Holds every tool the system knows about. ``openai_schemas()`` exposes only
non-privileged tools to the LLM; privileged tools stay registered (so they are
discoverable/auditable) but are hidden from the model and refuse execution.
"""

from __future__ import annotations

from backend.core.config import Settings
from backend.core.logging import get_logger
from backend.tools import browser, research, terminal
from backend.tools.schemas import Tool

logger = get_logger("gryphon.tools")


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


def create_default_registry(settings: Settings) -> ToolRegistry:
    """Build the Phase 0 registry with all built-in tools."""
    registry = ToolRegistry()
    terminal.register(registry, settings)
    research.register(registry, settings)
    browser.register(registry, settings)
    return registry
