"""Per-run execution context (Phase 1).

The agent sets the current ``run_id`` as a context-local value so any tool
that publishes its own events mid-execution (browser navigation, workflows)
can stamp them with the same run ID as the enclosing request. Falls back to
``None`` for events published outside a run.
"""

from __future__ import annotations

import contextvars

_current_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "griffin_run_id", default=None
)
_current_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "griffin_session_id", default=None
)
_current_task_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "griffin_task_id", default=None
)


def set_run_id(run_id: str | None) -> None:
    _current_run_id.set(run_id)


def get_run_id() -> str | None:
    return _current_run_id.get()


def set_session_id(session_id: str | None) -> None:
    _current_session_id.set(session_id)


def get_session_id() -> str | None:
    return _current_session_id.get()


def set_task_id(task_id: str | None) -> None:
    _current_task_id.set(task_id)


def get_task_id() -> str | None:
    return _current_task_id.get()
