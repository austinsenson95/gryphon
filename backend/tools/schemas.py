"""Tool contract (SPEC §2).

``ToolResult`` is the sacred JSON shape every tool execution returns, and
``Tool`` describes a registered capability: JSON-schema input, a permission
level, and an async handler.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from backend.core.permissions import Permission

ToolHandler = Callable[..., Awaitable[Any]]


class ToolErrorBody(BaseModel):
    code: str
    message: str


class ToolResult(BaseModel):
    success: bool
    tool: str
    data: dict | None = None
    error: ToolErrorBody | None = None

    @classmethod
    def ok(cls, tool: str, data: dict) -> "ToolResult":
        return cls(success=True, tool=tool, data=data, error=None)

    @classmethod
    def fail(cls, tool: str, code: str, message: str) -> "ToolResult":
        return cls(
            success=False,
            tool=tool,
            data=None,
            error=ToolErrorBody(code=code, message=message),
        )


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict  # JSON schema for the handler keyword arguments
    permission: Permission
    handler: ToolHandler
