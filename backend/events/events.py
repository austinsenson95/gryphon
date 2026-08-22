"""Event envelope + type constants (SPEC §2 Events).

Envelope JSON (exact):
{"id":"evt_<uuid>","type":"TOOL_CALL_STARTED","timestamp":"<UTC ISO8601 Z>",
 "session_id":"...","task_id":"...|null","data":{}}
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

    ALL = (
        SESSION_CREATED, MESSAGE_RECEIVED, AGENT_STARTED, AGENT_THINKING,
        TOOL_CALL_STARTED, TOOL_CALL_COMPLETED, TOOL_CALL_FAILED,
        AGENT_RESPONSE, TASK_STARTED, TASK_COMPLETED, TASK_FAILED,
        USER_APPROVAL_REQUIRED,
    )


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class EventEnvelope(BaseModel):
    id: str
    type: str
    timestamp: str
    session_id: str | None = None
    task_id: str | None = None
    data: dict = Field(default_factory=dict)


def new_event(
    type: str,
    session_id: str | None = None,
    task_id: str | None = None,
    data: dict | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        id=f"evt_{uuid.uuid4().hex}",
        type=type,
        timestamp=utc_iso_now(),
        session_id=session_id,
        task_id=task_id,
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
        data=row.data or {},
    )
