"""Tool permission model (Phase 1: LOW / MEDIUM / HIGH risk levels).

Enforcement vocabulary (kept for backward compatibility with the existing
registry and tests):

- ``safe``:      LOW risk — executes automatically.
- ``confirm``:   MEDIUM risk — requires user approval (Phase 1 auto-approves
                 immediately, emitting permission.required + permission.granted).
- ``privileged``: HIGH risk — never exposed to the LLM (excluded from
                 ``ToolRegistry.openai_schemas()``) and execution is refused
                 with a structured error.

The ``risk_level()`` helper maps each enforcement permission onto the
LOW/MEDIUM/HIGH vocabulary the spec defines.
"""

from __future__ import annotations

from typing import Literal

Permission = Literal["safe", "confirm", "privileged"]

SAFE: Permission = "safe"
CONFIRM: Permission = "confirm"
PRIVILEGED: Permission = "privileged"

ALL_PERMISSIONS: tuple[str, ...] = ("safe", "confirm", "privileged")

# Risk levels (spec §14): LOW auto-executes, MEDIUM requires approval,
# HIGH is refused.
RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]

LOW: RiskLevel = "LOW"
MEDIUM: RiskLevel = "MEDIUM"
HIGH: RiskLevel = "HIGH"

_RISK_FOR_PERMISSION: dict[Permission, RiskLevel] = {
    SAFE: LOW,
    CONFIRM: MEDIUM,
    PRIVILEGED: HIGH,
}


def risk_level(permission: Permission) -> RiskLevel:
    """Map an enforcement permission onto the LOW/MEDIUM/HIGH vocabulary."""
    return _RISK_FOR_PERMISSION.get(permission, HIGH)


def requires_approval(permission: Permission) -> bool:
    """True for MEDIUM-risk (confirm) tools that must pass the approval gate."""
    return permission == CONFIRM


def is_executable(permission: Permission) -> bool:
    """HIGH-risk (privileged) tools are registered but must never actually run."""
    return permission != PRIVILEGED
