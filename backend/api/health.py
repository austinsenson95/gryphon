"""GET /api/health"""

from __future__ import annotations

from fastapi import APIRouter, Request

from backend.core.config import APP_VERSION
from backend.core.state import get_state

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict:
    state = get_state(request)
    return {
        "status": "ok",
        "service": "gryphon",
        "version": APP_VERSION,
        "llm_mode": state.llm_mode,
    }
