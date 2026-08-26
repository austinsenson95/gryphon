"""Contacts, call jobs, and Vobiz webhook endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from backend.core.state import get_state

router = APIRouter(prefix="/api/phone", tags=["phone"])


class ContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone_number: str = Field(min_length=8, max_length=20)
    notes: str = Field(default="", max_length=500)


class CallCreate(BaseModel):
    contact_name: str = Field(min_length=1, max_length=120)
    mission: str = Field(min_length=1, max_length=2000)
    questions: list[str] = Field(default_factory=list, max_length=12)
    session_id: str | None = None


async def _payload(request: Request) -> dict[str, Any]:
    data: dict[str, Any] = dict(request.query_params)
    try:
        value = await request.json()
        if isinstance(value, dict):
            data.update(value)
            return data
    except Exception:
        pass
    try:
        data.update(dict(await request.form()))
    except Exception:
        pass
    return data


def _field(data: dict[str, Any], *names: str):
    lowered = {str(key).lower(): value for key, value in data.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def _check(request: Request, token: str | None) -> None:
    if not get_state(request).phone.verify_webhook(token):
        raise HTTPException(status_code=403, detail={"code": "INVALID_WEBHOOK_TOKEN", "message": "Invalid phone webhook token."})


@router.get("/status")
async def phone_status(request: Request) -> dict:
    return await get_state(request).phone.status()


@router.get("/contacts")
async def contacts(request: Request) -> list[dict]:
    return await get_state(request).phone.list_contacts()


@router.post("/contacts", status_code=201)
async def add_contact(body: ContactCreate, request: Request) -> dict:
    try:
        return await get_state(request).phone.create_contact(body.name, body.phone_number, body.notes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "CONTACT_INVALID", "message": str(exc)}) from exc


@router.get("/calls")
async def calls(request: Request, limit: int = Query(default=50, ge=1, le=200)) -> list[dict]:
    return await get_state(request).phone.list_calls(limit)


@router.get("/calls/{call_id}")
async def call(call_id: str, request: Request) -> dict:
    value = await get_state(request).phone.get_call(call_id)
    if value is None:
        raise HTTPException(status_code=404, detail={"code": "CALL_NOT_FOUND", "message": "Call not found."})
    return value


@router.post("/calls", status_code=202)
async def start_call(body: CallCreate, request: Request) -> dict:
    try:
        return await get_state(request).phone.start_call(
            contact_name=body.contact_name,
            mission=body.mission,
            questions=body.questions,
            session_id=body.session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "CALL_INVALID", "message": str(exc)}) from exc


@router.post("/calls/{call_id}/cancel")
async def cancel_call(call_id: str, request: Request) -> dict:
    try:
        return await get_state(request).phone.cancel(call_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": "CALL_NOT_FOUND", "message": str(exc)}) from exc


@router.api_route("/webhooks/vobiz/answer", methods=["GET", "POST"])
async def vobiz_answer(request: Request, job_id: str, token: str | None = None):
    _check(request, token)
    data = await _payload(request)
    provider_id = _field(data, "CallUUID", "request_uuid", "call_uuid", "call_sid")
    try:
        xml = await get_state(request).phone.answer(job_id, str(provider_id) if provider_id else None)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": "CALL_NOT_FOUND", "message": str(exc)}) from exc
    return PlainTextResponse(xml, media_type="application/xml")


@router.api_route("/webhooks/vobiz/recording", methods=["GET", "POST"])
async def vobiz_recording(request: Request, job_id: str, token: str | None = None):
    _check(request, token)
    data = await _payload(request)
    user_text = _field(data, "user_text", "transcription", "text", "speech")
    recording_url = _field(data, "recording_url", "RecordingUrl", "record_url", "audio_url", "url")
    try:
        xml = await get_state(request).phone.recording(
            job_id,
            str(user_text) if user_text else None,
            str(recording_url) if recording_url else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": "CALL_NOT_FOUND", "message": str(exc)}) from exc
    return PlainTextResponse(xml, media_type="application/xml")


@router.api_route("/webhooks/vobiz/hangup", methods=["GET", "POST"])
async def vobiz_hangup(request: Request, job_id: str, token: str | None = None):
    _check(request, token)
    data = await _payload(request)
    raw_duration = _field(data, "duration_seconds", "Duration", "call_duration")
    try:
        duration = int(float(raw_duration)) if raw_duration is not None else None
    except (TypeError, ValueError):
        duration = None
    try:
        await get_state(request).phone.hangup(job_id, duration)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": "CALL_NOT_FOUND", "message": str(exc)}) from exc
    return PlainTextResponse("", status_code=204)
