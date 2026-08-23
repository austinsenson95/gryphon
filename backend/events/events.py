"""Event envelope + type constants (SPEC §2, extended for Phase 1).

Envelope JSON (exact):
{"id":"evt_<uuid>","type":"TOOL_CALL_STARTED","timestamp":"<UTC ISO8601 Z>",
 "session_id":"...|null","task_id":"...|null","run_id":"...|null","data":{}}

Every event published during one user request carries the same ``run_id`` so
the whole execution is representable as one unit (§9).

Event names follow the existing normalized UPPER_SNAKE convention. The spec's
dotted names map 1:1 onto them:

  agent.started      == AGENT_STARTED         tool.completed    == TOOL_CALL_COMPLETED
  agent.thinking     == AGENT_THINKING        tool.failed       == TOOL_CALL_FAILED
  agent.completed    == AGENT_RESPONSE (+ TASK_COMPLETED)
  agent.failed       == TASK_FAILED
  tool.started       == TOOL_CALL_STARTED
  permission.required== PERMISSION_REQUIRED   permission.granted== PERMISSION_GRANTED
  permission.denied  == PERMISSION_DENIED
  browser.navigation == BROWSER_NAVIGATION    browser.page_loaded == BROWSER_PAGE_LOADED
  workflow.started   == WORKFLOW_STARTED      workflow.completed == WORKFLOW_COMPLETED
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class EventType:
    SESSION_CREATED = "SESSION_CREATED"
    MESSAGE_RECEIVED = "MESSAGE_RECEIVED"
    AGENT_STARTED = "AGENT_STARTED"
    AGENT_THINKING = "AGENT_THINKING"
    TOOL_CALL_STARTED = "TOOL_CALL_STARTED"
    TOOL_CALL_COMPLETED = "TOOL_CALL_COMPLETED"
    TOOL_CALL_FAILED = "TOOL_CALL_FAILED"
    AGENT_RESPONSE = "AGENT_RESPONSE"
    TASK_STARTED = "TASK_STARTED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    USER_APPROVAL_REQUIRED = "USER_APPROVAL_REQUIRED"
    STT_STARTED = "STT_STARTED"
    STT_COMPLETED = "STT_COMPLETED"
    STT_FAILED = "STT_FAILED"
    WORKFLOW_STARTED = "WORKFLOW_STARTED"
    WORKFLOW_COMPLETED = "WORKFLOW_COMPLETED"

    # Phase 1 additions
    PERMISSION_REQUIRED = "PERMISSION_REQUIRED"
    PERMISSION_GRANTED = "PERMISSION_GRANTED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    BROWSER_NAVIGATION = "BROWSER_NAVIGATION"
    BROWSER_PAGE_LOADED = "BROWSER_PAGE_LOADED"
    REMOTE_SESSION_STARTED = "REMOTE_SESSION_STARTED"
    REMOTE_DEVICE_PAIRED = "REMOTE_DEVICE_PAIRED"
    REMOTE_SESSION_STOPPED = "REMOTE_SESSION_STOPPED"

    ALL = (
        SESSION_CREATED, MESSAGE_RECEIVED, AGENT_STARTED, AGENT_THINKING,
        TOOL_CALL_STARTED, TOOL_CALL_COMPLETED, TOOL_CALL_FAILED,
        AGENT_RESPONSE, TASK_STARTED, TASK_COMPLETED, TASK_FAILED,
        USER_APPROVAL_REQUIRED,
        STT_STARTED, STT_COMPLETED, STT_FAILED,
        WORKFLOW_STARTED, WORKFLOW_COMPLETED,
        PERMISSION_REQUIRED, PERMISSION_GRANTED, PERMISSION_DENIED,
        BROWSER_NAVIGATION, BROWSER_PAGE_LOADED,
    )


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class EventEnvelope(BaseModel):
    id: str
    type: str
    timestamp: str
    session_id: str | None = None
    task_id: str | None = None
    run_id: str | None = None
    data: dict = Field(default_factory=dict)


def new_event(
    type: str,
    session_id: str | None = None,
    task_id: str | None = None,
    run_id: str | None = None,
    data: dict | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        id=f"evt_{uuid.uuid4().hex}",
        type=type,
        timestamp=utc_iso_now(),
        session_id=session_id,
        task_id=task_id,
        run_id=run_id,
        data=data or {},
    )


def envelope_from_row(row) -> EventEnvelope:
    """Serialize a persisted ``events`` table row back into an envelope."""
    from backend.memory.retrieval import iso  # local import: keeps events/ db-agnostic at module load

    return EventEnvelope(
        id=row.id,
        type=row.type,
        timestamp=iso(row.created_at) or "",
        session_id=row.session_id,
        task_id=row.task_id,
        run_id=getattr(row, "run_id", None),
        data=row.data or {},
    )
