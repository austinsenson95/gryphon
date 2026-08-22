"""Tool executor: runs a tool through the registry with a timeout and always
returns a structured ``ToolResult`` — unknown tools, privileged tools, timeouts
and handler crashes never propagate as exceptions."""

from __future__ import annotations

import asyncio

from backend.core.logging import get_logger
from backend.core.permissions import is_executable
from backend.tools.registry import ToolRegistry
from backend.tools.schemas import ToolResult

logger = get_logger("gryphon.executor")

DEFAULT_TIMEOUT_SECONDS = 30.0


async def execute_tool(
    registry: ToolRegistry,
    name: str,
    arguments: dict | None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> ToolResult:
    tool = registry.get(name)
    if tool is None:
        return ToolResult.fail(name, "TOOL_NOT_FOUND", f"Unknown tool: {name}")
    if not is_executable(tool.permission):
        return ToolResult.fail(
            name,
            "PERMISSION_DENIED",
            f"Tool {name} is privileged and cannot be executed in Phase 0.",
        )
    arguments = arguments or {}
    try:
        result = await asyncio.wait_for(tool.handler(**arguments), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("executor.timeout", extra={"tool": name})
        return ToolResult.fail(name, "TOOL_TIMEOUT", f"Tool {name} timed out after {timeout}s")
    except TypeError as exc:
        return ToolResult.fail(name, "INVALID_ARGUMENTS", f"Invalid arguments for {name}: {exc}")
    except Exception as exc:
        logger.exception("executor.error", extra={"tool": name})
        return ToolResult.fail(name, "TOOL_EXECUTION_ERROR", str(exc))
    if isinstance(result, ToolResult):
        return result
    if isinstance(result, dict):
        return ToolResult.ok(name, result)
    return ToolResult.ok(name, {"result": result})
