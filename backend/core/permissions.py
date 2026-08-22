"""Tool permission model.

- ``safe``: executes automatically.
- ``confirm``: requires user approval. Phase 0 emits a USER_APPROVAL_REQUIRED
  event and then auto-approves (documented in the agent runtime).
- ``privileged``: never exposed to the LLM (excluded from
  ``ToolRegistry.openai_schemas()``) and execution is refused with a
  structured error.
"""

from __future__ import annotations

from typing import Literal

Permission = Literal["safe", "confirm", "privileged"]

SAFE: Permission = "safe"
CONFIRM: Permission = "confirm"
PRIVILEGED: Permission = "privileged"

ALL_PERMISSIONS: tuple[str, ...] = ("safe", "confirm", "privileged")


def requires_approval(permission: Permission) -> bool:
    return permission == "confirm"


def is_executable(permission: Permission) -> bool:
    """Privileged tools are registered but must never actually run."""
    return permission != "privileged"
