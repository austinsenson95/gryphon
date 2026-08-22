"""GET /api/events?limit=50 — recent events in chronological order."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from backend.core.state import get_state
from backend.memory import retrieval
from backend.events.events import envelope_from_row

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events")
async def get_events(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict]:
    state = get_state(request)
    async with state.db.session_factory() as session:
        rows = await repository.get_recent_events(session, limit=limit)
    return [envelope_from_row(row).model_dump() for row in rows]
