"""Health endpoints: /api/health plus subsystem checks (ollama/stt/tools)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from backend.core.config import APP_VERSION
from backend.core.state import get_state
from backend.llm.ollama import OllamaProvider

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


@router.get("/health/ollama")
async def health_ollama(request: Request) -> dict:
    """Ollama reachability + model presence + inference probe."""
    state = get_state(request)
    if isinstance(state.provider, OllamaProvider):
        return await state.provider.health_check()
    return {
        "provider": state.settings.llm_provider,
        "reachable": False,
        "model_available": False,
        "inference_ok": False,
        "error": (
            "Ollama is not the active LLM provider "
            f"(LLM_PROVIDER={state.settings.llm_provider}, mode={state.llm_mode})."
        ),
    }


@router.get("/health/stt")
async def health_stt(request: Request) -> dict:
    state = get_state(request)
    return await state.stt.health()


@router.get("/health/tools")
async def health_tools(request: Request) -> dict:
    """Command registry inventory — what Gryphon is currently able to execute."""
    state = get_state(request)
    tools = [
        {
            "name": tool.name,
            "description": tool.description,
            "permission": tool.permission,
            "exposed_to_llm": tool.permission != "privileged",
        }
        for tool in state.registry.list()
    ]
    return {"status": "ok", "count": len(tools), "tools": tools}
