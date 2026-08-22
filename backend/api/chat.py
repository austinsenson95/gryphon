"""POST /api/chat — run the agent synchronously within the request.

Events stream to /ws clients while the agent works. Sessions are created on
demand (emitting SESSION_CREATED) when no valid session_id is supplied.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from backend.core.agent import Agent
from backend.core.state import get_state
from backend.events.events import EventType, new_event
from backend.services.message_service import MessageService

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None


class ChatResponse(BaseModel):
    message_id: str
    task_id: str
    session_id: str
    response: str
    tool_calls: list[dict]
    error: dict | None = None


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    state = get_state(request)
    messages = MessageService(state.db.session_factory)

    session_id = body.session_id
    if session_id:
        existing = await messages.get_session(session_id)
        if existing is None:
            session_id = None
    if not session_id:
        title = body.message[:60]
        session = await messages.create_session(title=title)
        session_id = session.id
        await state.bus.publish(
            new_event(
                EventType.SESSION_CREATED,
                session_id=session_id,
                data={"session_id": session_id, "title": title},
            )
        )

    agent = Agent(
        db=state.db,
        bus=state.bus,
        registry=state.registry,
        provider=state.provider,
        settings=state.settings,
    )
    result = await agent.run(session_id, body.message)
    return ChatResponse(**result.model_dump())
