"""LLM provider management endpoints.

Allows the dashboard to query and switch the active provider at runtime
(e.g., Ollama vs xAI) without restarting the backend.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.core.state import get_state

router = APIRouter(prefix="/api", tags=["llm"])

AVAILABLE_PROVIDERS = ["ollama", "xai"]


class ProviderInfo(BaseModel):
    provider: str
    mode: str
    available: list[str]


class ProviderSwitchRequest(BaseModel):
    provider: str = Field(min_length=1)


@router.get("/llm/provider", response_model=ProviderInfo)
async def get_provider(request: Request) -> ProviderInfo:
    state = get_state(request)
    return ProviderInfo(
        provider=state.active_provider_name,
        mode=state.llm_mode,
        available=AVAILABLE_PROVIDERS,
    )


@router.post("/llm/provider", response_model=ProviderInfo)
async def set_provider(body: ProviderSwitchRequest, request: Request) -> ProviderInfo:
    state = get_state(request)
    if body.provider not in AVAILABLE_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_PROVIDER",
                "message": f"Provider must be one of {AVAILABLE_PROVIDERS}",
            },
        )
    state.set_provider(body.provider)
    return ProviderInfo(
        provider=state.active_provider_name,
        mode=state.llm_mode,
        available=AVAILABLE_PROVIDERS,
    )
