from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.core.state import get_state
from backend.tools.whatsapp.exceptions import WhatsAppError

router = APIRouter(prefix="/api/tools/whatsapp", tags=["whatsapp"])


class SearchBody(BaseModel):
    query: str = Field(min_length=1, max_length=120)


class PrepareBody(BaseModel):
    recipient: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1)


class SendBody(BaseModel):
    approval_token: str = Field(min_length=20)


def _raise(exc: Exception):
    code = getattr(exc, "code", "WHATSAPP_INVALID_INPUT")
    status = 409 if "APPROVAL" in code or "AMBIGUOUS" in code else 400
    raise HTTPException(status_code=status, detail={"code": code, "message": str(exc)}) from exc


@router.get("/status")
async def status(request: Request):
    return await get_state(request).whatsapp.status()


@router.post("/open")
async def open_whatsapp(request: Request):
    try:
        return await get_state(request).whatsapp.open()
    except Exception as exc:
        _raise(exc)


@router.delete("/session")
async def disconnect(request: Request):
    return await get_state(request).whatsapp.disconnect()


@router.post("/search")
async def search(body: SearchBody, request: Request):
    try:
        return await get_state(request).whatsapp.search_contact(body.query)
    except (WhatsAppError, ValueError) as exc:
        _raise(exc)


@router.post("/prepare", status_code=201)
async def prepare(body: PrepareBody, request: Request):
    try:
        return await get_state(request).whatsapp.prepare_message(body.recipient, body.message)
    except (WhatsAppError, ValueError) as exc:
        _raise(exc)


@router.get("/actions")
async def actions(request: Request, limit: int = Query(default=20, ge=1, le=100)):
    return await get_state(request).whatsapp.list_actions(limit)


@router.post("/actions/{action_id}/approve")
async def approve(action_id: str, request: Request):
    try:
        return await get_state(request).whatsapp.approve(action_id)
    except WhatsAppError as exc:
        _raise(exc)


@router.post("/actions/{action_id}/send")
async def send(action_id: str, body: SendBody, request: Request):
    try:
        return await get_state(request).whatsapp.send(action_id, body.approval_token)
    except WhatsAppError as exc:
        _raise(exc)


@router.post("/actions/{action_id}/cancel")
async def cancel(action_id: str, request: Request):
    try:
        return await get_state(request).whatsapp.cancel(action_id)
    except WhatsAppError as exc:
        _raise(exc)
