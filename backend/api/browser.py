"""GET /api/browser — lightweight Griffin browser status (§21).

Lets the dashboard show whether the browser is active and what page it is
currently on. No remote streaming — the browser stays local to the Mac.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from backend.core.state import get_state

router = APIRouter(prefix="/api", tags=["browser"])


@router.get("/browser")
async def browser_status(request: Request) -> dict:
    state = get_state(request)
    manager = getattr(state.registry, "browser", None)
    if manager is None:
        return {"active": False, "mock": True, "url": None, "title": None}
    return await manager.status()
