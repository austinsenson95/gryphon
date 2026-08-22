"""System tools: local, always-available capabilities."""

from __future__ import annotations

import platform
import socket
from datetime import datetime

from backend.core.config import APP_VERSION, Settings
from backend.tools.schemas import Tool, ToolResult


async def _get_time() -> dict:
    now = datetime.now().astimezone()
    return {
        "iso": now.isoformat(),
        "unix": int(now.timestamp()),
        "timezone": now.tzname() or "local",
        "human": now.strftime("%A, %B %d, %Y at %H:%M:%S"),
    }


async def _get_info(settings: Settings) -> dict:
    return {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "hostname": socket.gethostname(),
        "app": settings.app_name,
        "version": APP_VERSION,
        "environment": settings.environment,
    }


async def _execute_shell(command: str) -> ToolResult:
    """Privileged stub: registered for the roadmap, refuses to run in Phase 0."""
    return ToolResult.fail(
        tool="system.execute_shell",
        code="PERMISSION_DENIED",
        message=(
            "system.execute_shell is a privileged tool and is disabled in "
            "Phase 0 (no unrestricted shell execution)."
        ),
    )


def register(registry, settings: Settings) -> None:
    async def get_time() -> dict:
        return await _get_time()

    async def get_info() -> dict:
        return await _get_info(settings)

    registry.register(
        Tool(
            name="system.get_time",
            description="Get the current local server time (ISO, unix, timezone, human-readable).",
            input_schema={"type": "object", "properties": {}, "required": []},
            permission="safe",
            handler=get_time,
        )
    )
    registry.register(
        Tool(
            name="system.get_info",
            description="Get information about the Gryphon host system and runtime.",
            input_schema={"type": "object", "properties": {}, "required": []},
            permission="safe",
            handler=get_info,
        )
    )
    registry.register(
        Tool(
            name="system.execute_shell",
            description=(
                "[PRIVILEGED — disabled in Phase 0] Execute a shell command on "
                "the host. Registered for future phases; refuses execution."
            ),
            input_schema={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
            permission="privileged",
            handler=_execute_shell,
        )
    )
