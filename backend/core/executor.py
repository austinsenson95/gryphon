"""Tool executor: runs a tool through the registry with a timeout and always
returns a structured ``ToolResult`` — unknown tools, privileged tools, timeouts
and handler crashes never propagate as exceptions.

Transient failures (timeouts) are retried a bounded number of times
(``max_retries``, default 0 = no retries). Deterministic failures (invalid
arguments, unknown tool, permission denials) are never retried.
"""

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
    max_retries: int = 0,
) -> ToolResult:
    tool = registry.get(name)
    if tool is None:
        return ToolResult.fail(name, "TOOL_NOT_FOUND", f"Unknown tool: {name}")
    if not is_executable(tool.permission):
        return ToolResult.fail(
            name,
            "PERMISSION_DENIED",
            f"Tool {name} is privileged and cannot be executed.",
        )
    arguments = arguments or {}

    attempt = 0
    while True:
        result = await _run_once(tool, arguments, timeout)
        # Only transient timeouts are worth a bounded retry.
        if result.success or result.error is None or result.error.code != "TOOL_TIMEOUT":
            return result
        if attempt >= max_retries:
            return result
        attempt += 1
        logger.info(
            "executor.retry",
            extra={"tool": name, "attempt": attempt, "max_retries": max_retries},
        )


async def _run_once(tool, arguments: dict, timeout: float) -> ToolResult:
    name = tool.name
    try:
        result = await asyncio.wait_for(tool.handler(**arguments), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("executor.timeout", extra={"tool": name, "timeout": timeout})
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
