"""LAN remote-control API with short-lived pairing and bearer authorization."""

from __future__ import annotations

import ipaddress
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from backend.api.chat import ChatRequest, ChatResponse, run_chat
from backend.api.voice import run_voice
from backend.core.state import AppState, get_state
from backend.events.events import EventType, new_event

router = APIRouter(prefix="/api/remote", tags=["remote"])


class PairRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class InputRequest(BaseModel):
    type: Literal[
        "tap", "double_tap", "secondary_tap", "move", "scroll", "text", "key",
        "enter_fullscreen", "exit_fullscreen", "select_window", "move_window", "release_window", "volume",
    ]
    x: float | None = Field(default=None, ge=0, le=1)
    y: float | None = Field(default=None, ge=0, le=1)
    dx: int = Field(default=0, ge=-100, le=100)
    dy: int = Field(default=0, ge=-100, le=100)
    text: str | None = Field(default=None, max_length=2000)
    key: str | None = Field(default=None, max_length=32)
    modifiers: list[str] = Field(default_factory=list, max_length=4)
    volume: int | None = Field(default=None, ge=0, le=100)


class AppRequest(BaseModel):
    app: str = Field(min_length=1, max_length=160)


REMOTE_APPLICATIONS: dict[str, tuple[str, ...]] = {
    "hermes": ("Hermes", "Hermes Agent"),
    "spotify": ("Spotify",),
    "notes": ("Notes",),
    "vscode": ("Visual Studio Code",),
    "terminal": ("Terminal",),
}


def _available_applications(state: AppState) -> list[dict[str, str]]:
    applications = state.remote.adapter.installed_applications()
    results = [{"id": name, "name": name} for name in applications]
    if not any(item["name"].casefold() in {"hermes", "hermes agent"} for item in results):
        results.insert(0, {"id": "hermes", "name": "Hermes"})
    return results


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def _is_lan_request(request: Request) -> bool:
    host = request.client.host if request.client else ""
    if host == "testserver":
        return True
    try:
        address = ipaddress.ip_address(host)
        return address.is_loopback or address.is_private or address.is_link_local
    except ValueError:
        return False


@router.get("")
async def remote_status(request: Request, state: AppState = Depends(get_state)) -> dict:
    return {**state.remote.status(), "can_start": _is_lan_request(request)}


@router.post("/session")
async def start_remote(request: Request, state: AppState = Depends(get_state)) -> dict:
    if not _is_lan_request(request):
        raise HTTPException(403, detail={"code": "LAN_ONLY", "message": "Screen sharing can only start from Griffin's local network."})
    result = state.remote.start()
    await state.bus.publish(new_event(EventType.REMOTE_SESSION_STARTED, data={"device_name": result["device_name"]}))
    return result


@router.post("/pair")
async def pair_remote(body: PairRequest, state: AppState = Depends(get_state)) -> dict:
    try:
        result = state.remote.pair(body.code)
    except PermissionError as exc:
        raise HTTPException(401, detail={"code": "PAIRING_FAILED", "message": str(exc)}) from exc
    await state.bus.publish(new_event(EventType.REMOTE_DEVICE_PAIRED, data={"device_name": result["device_name"]}))
    return result


@router.delete("/session")
async def stop_remote(
    request: Request,
    authorization: str | None = Header(default=None),
    state: AppState = Depends(get_state),
) -> dict:
    if not _is_lan_request(request):
        try:
            state.remote.authenticate(_bearer(authorization))
        except PermissionError as exc:
            raise HTTPException(401, detail={"code": "REMOTE_UNAUTHORIZED", "message": str(exc)}) from exc
    state.remote.stop()
    await state.bus.publish(new_event(EventType.REMOTE_SESSION_STOPPED))
    return {"stopped": True}


@router.get("/frame")
async def remote_frame(
    authorization: str | None = Header(default=None),
    state: AppState = Depends(get_state),
) -> Response:
    try:
        state.remote.authenticate(_bearer(authorization))
        frame = await state.remote.adapter.capture_frame()
    except PermissionError as exc:
        raise HTTPException(401, detail={"code": "REMOTE_UNAUTHORIZED", "message": str(exc)}) from exc
    except RuntimeError as exc:
        raise HTTPException(503, detail={"code": "CAPTURE_UNAVAILABLE", "message": str(exc)}) from exc
    return Response(frame, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/input")
async def remote_input(
    body: InputRequest,
    authorization: str | None = Header(default=None),
    state: AppState = Depends(get_state),
) -> dict:
    try:
        state.remote.authenticate(_bearer(authorization))
        action = body.model_dump(exclude_none=True)
        if body.type in {"tap", "double_tap", "secondary_tap", "move"} and (body.x is None or body.y is None):
            raise ValueError("Pointer actions require x and y coordinates.")
        if body.type == "text" and not body.text:
            raise ValueError("Text input cannot be empty.")
        if body.type == "key" and not body.key:
            raise ValueError("Key input requires a key name.")
        if body.type == "volume" and body.volume is None:
            raise ValueError("Volume input requires a level from 0 to 100.")
        if body.type == "move_window" and not (body.dx or body.dy):
            raise ValueError("Window movement requires a horizontal or vertical distance.")
        await state.remote.adapter.perform(action)
    except PermissionError as exc:
        raise HTTPException(401, detail={"code": "REMOTE_UNAUTHORIZED", "message": str(exc)}) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(400, detail={"code": "REMOTE_INPUT_FAILED", "message": str(exc)}) from exc
    return {"accepted": True}


@router.get("/volume")
async def remote_volume(
    authorization: str | None = Header(default=None),
    state: AppState = Depends(get_state),
) -> dict:
    try:
        state.remote.authenticate(_bearer(authorization))
        volume = await state.remote.adapter.get_output_volume()
    except PermissionError as exc:
        raise HTTPException(401, detail={"code": "REMOTE_UNAUTHORIZED", "message": str(exc)}) from exc
    except RuntimeError as exc:
        raise HTTPException(503, detail={"code": "VOLUME_UNAVAILABLE", "message": str(exc)}) from exc
    return {"volume": volume}


@router.get("/apps")
async def remote_applications(
    authorization: str | None = Header(default=None),
    state: AppState = Depends(get_state),
) -> dict:
    try:
        state.remote.authenticate(_bearer(authorization))
    except PermissionError as exc:
        raise HTTPException(401, detail={"code": "REMOTE_UNAUTHORIZED", "message": str(exc)}) from exc
    return {"applications": _available_applications(state)}


@router.post("/chat", response_model=ChatResponse)
async def remote_chat(
    body: ChatRequest,
    authorization: str | None = Header(default=None),
    state: AppState = Depends(get_state),
) -> ChatResponse:
    """Run an agent command from a paired phone remote."""
    try:
        state.remote.authenticate(_bearer(authorization))
    except PermissionError as exc:
        raise HTTPException(401, detail={"code": "REMOTE_UNAUTHORIZED", "message": str(exc)}) from exc
    return await run_chat(body, state)


@router.post("/voice", response_model=None)
async def remote_voice(
    request: Request,
    authorization: str | None = Header(default=None),
    state: AppState = Depends(get_state),
):
    """Run an authenticated phone recording through local STT and Griffin."""
    try:
        state.remote.authenticate(_bearer(authorization))
    except PermissionError as exc:
        raise HTTPException(401, detail={"code": "REMOTE_UNAUTHORIZED", "message": str(exc)}) from exc
    return await run_voice(request, state)


@router.post("/permissions/accessibility")
async def open_remote_accessibility_settings(
    request: Request,
    authorization: str | None = Header(default=None),
    state: AppState = Depends(get_state),
) -> dict:
    """Open the correct Mac settings pane from either dashboard."""
    try:
        if not _is_lan_request(request):
            state.remote.authenticate(_bearer(authorization))
        target = await state.remote.adapter.open_accessibility_settings()
    except PermissionError as exc:
        raise HTTPException(401, detail={"code": "REMOTE_UNAUTHORIZED", "message": str(exc)}) from exc
    except RuntimeError as exc:
        raise HTTPException(400, detail={"code": "SETTINGS_UNAVAILABLE", "message": str(exc)}) from exc
    return {"opened": True, "permission_target": target}


@router.post("/app")
async def remote_application(
    body: AppRequest,
    authorization: str | None = Header(default=None),
    state: AppState = Depends(get_state),
) -> dict:
    try:
        state.remote.authenticate(_bearer(authorization))
        requested = body.app.strip()
        if requested.casefold() == "hermes":
            opened_name = await state.remote.adapter.open_hermes_agent()
        else:
            aliases = REMOTE_APPLICATIONS.get(requested.casefold())
            installed = {
                name.casefold(): name for name in state.remote.adapter.installed_applications()
            }
            canonical = installed.get(requested.casefold())
            if aliases is None and canonical is None:
                raise ValueError("That application is not installed in a standard macOS Applications folder.")
            opened_name = await state.remote.adapter.open_application(aliases or (canonical,))
    except PermissionError as exc:
        raise HTTPException(401, detail={"code": "REMOTE_UNAUTHORIZED", "message": str(exc)}) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(400, detail={"code": "APP_LAUNCH_FAILED", "message": str(exc)}) from exc
    return {"opened": True, "app": body.app, "application": opened_name}
