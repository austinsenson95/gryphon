"""POST /api/voice — transcribe uploaded audio locally, then run the agent.

The browser sends raw audio bytes (MediaRecorder output) in the request body;
no multipart dependency. The audio is written to a temp file, transcribed by
the configured local STT provider, and the transcript flows through the exact
same agent pipeline as typed text. STT lifecycle events stream to /ws.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.core.agent import Agent
from backend.core.state import AppState, get_state
from backend.events.events import EventType, new_event
from backend.services.message_service import MessageService
from backend.stt.base import STTError, STTUnavailableError

router = APIRouter(prefix="/api", tags=["voice"])

_MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB cap

_CONTENT_TYPE_SUFFIX = {
    "audio/webm": ".webm",
    "audio/mp4": ".mp4",
    "audio/m4a": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/ogg": ".ogg",
    "audio/flac": ".flac",
    "audio/aac": ".aac",
}


class VoiceResponse(BaseModel):
    transcript: str
    run_id: str
    message_id: str
    task_id: str
    session_id: str
    response: str
    tool_calls: list[dict]
    error: dict | None = None


def _error(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"error": {"code": code, "message": message}}
    )


@router.post("/voice", response_model=None)
async def voice(request: Request):
    state = get_state(request)
    return await run_voice(request, state)


async def run_voice(request: Request, state: AppState):
    """Transcribe request audio and execute it through Griffin's agent."""

    audio = await request.body()
    if not audio:
        return _error("VALIDATION_ERROR", "Request body must contain audio data.", 422)
    if len(audio) > _MAX_AUDIO_BYTES:
        return _error("VALIDATION_ERROR", "Audio payload is too large (max 25 MB).", 422)

    content_type = (request.headers.get("content-type") or "").split(";")[0].strip()
    if content_type and not content_type.startswith("audio/"):
        return _error(
            "UNSUPPORTED_AUDIO",
            "Voice input accepts microphone audio only; video uploads are not allowed.",
            415,
        )
    session_id = request.headers.get("x-session-id") or None

    await state.bus.publish(
        new_event(EventType.STT_STARTED, session_id=session_id, data={})
    )

    suffix = _CONTENT_TYPE_SUFFIX.get(content_type, ".audio")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(audio)
        tmp.close()
        try:
            transcript = await state.stt.transcribe(tmp.name, content_type)
        except STTUnavailableError as exc:
            await state.bus.publish(
                new_event(
                    EventType.STT_FAILED,
                    session_id=session_id,
                    data={"error": {"code": "STT_UNAVAILABLE", "message": str(exc)}},
                )
            )
            return _error(
                "STT_UNAVAILABLE",
                "Voice transcription isn't available: no local speech-to-text "
                "engine is installed or configured.",
                503,
            )
        except STTError as exc:
            await state.bus.publish(
                new_event(
                    EventType.STT_FAILED,
                    session_id=session_id,
                    data={"error": {"code": "STT_FAILED", "message": str(exc)}},
                )
            )
            return _error(
                "STT_FAILED",
                "I couldn't transcribe that audio. Please try again or type instead.",
                500,
            )
    finally:
        Path(tmp.name).unlink(missing_ok=True)

    transcript = transcript.strip()
    if not transcript:
        await state.bus.publish(
            new_event(
                EventType.STT_FAILED,
                session_id=session_id,
                data={"error": {"code": "STT_EMPTY", "message": "Empty transcript"}},
            )
        )
        return _error(
            "STT_EMPTY", "I didn't catch anything — please try again.", 422
        )

    messages = MessageService(state.db.session_factory)
    if session_id:
        existing = await messages.get_session(session_id)
        if existing is None:
            session_id = None
    if not session_id:
        session = await messages.create_session(title=transcript[:60])
        session_id = session.id
        await state.bus.publish(
            new_event(
                EventType.SESSION_CREATED,
                session_id=session_id,
                data={"session_id": session_id, "title": transcript[:60]},
            )
        )

    await state.bus.publish(
        new_event(
            EventType.STT_COMPLETED,
            session_id=session_id,
            data={"transcript": transcript},
        )
    )

    agent = Agent(
        db=state.db,
        bus=state.bus,
        registry=state.registry,
        provider=state.provider,
        settings=state.settings,
    )
    result = await agent.run(session_id, transcript)
    return VoiceResponse(transcript=transcript, **result.model_dump())
