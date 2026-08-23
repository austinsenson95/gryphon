"""LAN remote-control API with short-lived pairing and bearer authorization."""

from __future__ import annotations

import ipaddress
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from backend.core.state import AppState, get_state
from backend.events.events import EventType, new_event

router = APIRouter(prefix="/api/remote", tags=["remote"])


class PairRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class InputRequest(BaseModel):
    type: Literal[
        "tap", "double_tap", "secondary_tap", "move", "scroll", "text", "key",
        "enter_fullscreen", "exit_fullscreen",
    ]
    x: float | None = Field(default=None, ge=0, le=1)
    y: float | None = Field(default=None, ge=0, le=1)
    dx: int = Field(default=0, ge=-100, le=100)
    dy: int = Field(default=0, ge=-100, le=100)
    text: str | None = Field(default=None, max_length=2000)
    key: str | None = Field(default=None, max_length=32)
    modifiers: list[str] = Field(default_factory=list, max_length=4)


class AppRequest(BaseModel):
    app: Literal["hermes", "spotify", "notes", "vscode", "terminal"]


REMOTE_APPLICATIONS: dict[str, tuple[str, ...]] = {
    "hermes": ("Hermes", "Hermes Agent"),
    "spotify": ("Spotify",),
    "notes": ("Notes",),
    "vscode": ("Visual Studio Code",),
    "terminal": ("Terminal",),
}


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
        await state.remote.adapter.perform(action)
    except PermissionError as exc:
        raise HTTPException(401, detail={"code": "REMOTE_UNAUTHORIZED", "message": str(exc)}) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(400, detail={"code": "REMOTE_INPUT_FAILED", "message": str(exc)}) from exc
    return {"accepted": True}


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
        if body.app == "hermes":
            opened_name = await state.remote.adapter.open_hermes_agent()
        else:
            opened_name = await state.remote.adapter.open_application(REMOTE_APPLICATIONS[body.app])
    except PermissionError as exc:
        raise HTTPException(401, detail={"code": "REMOTE_UNAUTHORIZED", "message": str(exc)}) from exc
    except RuntimeError as exc:
        raise HTTPException(400, detail={"code": "APP_LAUNCH_FAILED", "message": str(exc)}) from exc
    return {"opened": True, "app": body.app, "application": opened_name}
