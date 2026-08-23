"""Clean data-access functions. Services and the agent use these; nothing else
touches the ORM directly. Every function commits before returning so events and
messages are durable even if a later step fails.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.memory.models import Event, Message, Notification, Session, Task, ToolCall


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------- sessions


async def create_session(session: AsyncSession, title: str = "") -> Session:
    row = Session(id=_new_id("ses"), title=title)
    session.add(row)
    await session.commit()
    return row


async def get_session(session: AsyncSession, session_id: str) -> Session | None:
    return await session.get(Session, session_id)


# ---------------------------------------------------------------- messages


async def add_message(
    session: AsyncSession,
    session_id: str,
    role: str,
    content: str,
    tool_name: str | None = None,
) -> Message:
    row = Message(
        id=_new_id("msg"),
        session_id=session_id,
        role=role,
        content=content,
        tool_name=tool_name,
    )
    session.add(row)
    await session.commit()
    return row


async def get_recent_messages(
    session: AsyncSession, session_id: str, limit: int = 20
) -> list[Message]:
    """Last `limit` messages for a session, in chronological order."""
    stmt = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(desc(Message.created_at), desc(Message.id))
        .limit(limit)
    )
    rows = list((await session.scalars(stmt)).all())
    rows.reverse()
    return rows


# ---------------------------------------------------------------- tasks


async def create_task(session: AsyncSession, session_id: str, input_text: str) -> Task:
    row = Task(id=_new_id("task"), session_id=session_id, status="pending", input=input_text)
    session.add(row)
    await session.commit()
    return row


async def get_task(session: AsyncSession, task_id: str) -> Task | None:
    return await session.get(Task, task_id)


async def set_task_status(
    session: AsyncSession,
    task_id: str,
    status: str,
    result: str | None = None,
    completed: bool = False,
) -> Task | None:
    row = await session.get(Task, task_id)
    if row is None:
        return None
    row.status = status
    if result is not None:
        row.result = result
    if completed:
        row.completed_at = datetime.now(timezone.utc)
    await session.commit()
    return row


# ---------------------------------------------------------------- events


async def add_event(
    session: AsyncSession,
    event_id: str,
    type: str,
    session_id: str | None,
    task_id: str | None,
    data: dict,
    run_id: str | None = None,
) -> Event:
    row = Event(
        id=event_id,
        type=type,
        session_id=session_id,
        task_id=task_id,
        run_id=run_id,
        data=data,
    )
    session.add(row)
    await session.commit()
    return row


async def get_recent_events(session: AsyncSession, limit: int = 50) -> list[Event]:
    """Last `limit` events, returned in chronological order."""
    stmt = select(Event).order_by(desc(Event.created_at), desc(Event.id)).limit(limit)
    rows = list((await session.scalars(stmt)).all())
    rows.reverse()
    return rows


# ---------------------------------------------------------------- tool calls


async def add_tool_call(
    session: AsyncSession,
    task_id: str,
    tool: str,
    input_data: dict,
    output: dict | None,
    success: bool,
) -> ToolCall:
    row = ToolCall(
        id=_new_id("tc"),
        task_id=task_id,
        tool=tool,
        input=input_data,
        output=output,
        success=success,
    )
    session.add(row)
    await session.commit()
    return row


async def get_tool_calls_for_task(session: AsyncSession, task_id: str) -> list[ToolCall]:
    stmt = (
        select(ToolCall)
        .where(ToolCall.task_id == task_id)
        .order_by(ToolCall.created_at, ToolCall.id)
    )
    return list((await session.scalars(stmt)).all())


# ---------------------------------------------------------------- notifications


async def add_notification(
    session: AsyncSession, level: str, title: str, body: str = ""
) -> Notification:
    row = Notification(id=_new_id("ntf"), level=level, title=title, body=body)
    session.add(row)
    await session.commit()
    return row


async def get_unread_notifications(session: AsyncSession) -> list[Notification]:
    stmt = select(Notification).where(Notification.read.is_(False)).order_by(Notification.created_at)
    return list((await session.scalars(stmt)).all())
