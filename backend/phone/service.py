"""Durable Vobiz call jobs adapted from the Kimi AI phone-agent MVP.

Calls are asynchronous: starting a mission returns immediately, while Vobiz
drives the answer/recording/hangup webhooks. Every state and transcript change
is persisted before it is broadcast to the dashboard.
"""

from __future__ import annotations

import html
import hashlib
import hmac
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from backend.core.config import Settings
from backend.core.logging import get_logger
from backend.events.events import EventType, new_event
from backend.memory import retrieval as repository

logger = get_logger("griffin.phone")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _e164(value: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", value.strip())
    # Griffin is currently configured for an Indian Vobiz DID. Accept the
    # familiar 10-digit mobile format from the Contacts UI and persist its
    # canonical E.164 equivalent in the call allowlist.
    if re.fullmatch(r"[6-9]\d{9}", cleaned):
        cleaned = f"+91{cleaned}"
    if not re.fullmatch(r"\+[1-9]\d{7,14}", cleaned):
        raise ValueError("Phone number must use E.164 format, for example +919876543210.")
    return cleaned


def _question_rows(mission: str, questions: list[str] | None) -> list[dict]:
    values = [q.strip() for q in (questions or []) if q and q.strip()]
    if not values:
        values = [f"Could you share the information requested for this mission: {mission.strip()}?"]
    return [{"id": f"q{index + 1}", "question": value, "required": True} for index, value in enumerate(values)]


def serialize_contact(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "phone_number": row.phone_number,
        "notes": row.notes,
        "call_authorized": True,
        "authorization_source": "saved_contact",
        "created_at": repository.iso(row.created_at),
    }


def serialize_call(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "contact_id": row.contact_id,
        "contact_name": row.contact_name,
        "phone_number": row.phone_number,
        "mission": row.mission,
        "questions": row.questions or [],
        "status": row.status,
        "provider_call_id": row.provider_call_id,
        "session_id": row.session_id,
        "task_id": row.task_id,
        "transcript": row.transcript or [],
        "findings": row.findings or {},
        "summary": row.summary,
        "error": row.error,
        "duration_seconds": row.duration_seconds,
        "created_at": repository.iso(row.created_at),
        "started_at": repository.iso(row.started_at),
        "answered_at": repository.iso(row.answered_at),
        "ended_at": repository.iso(row.ended_at),
        "updated_at": repository.iso(row.updated_at),
    }


class PhoneService:
    def __init__(self, settings: Settings, session_factory, bus) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.bus = bus

    async def seed_contacts(self) -> None:
        async with self.session_factory() as session:
            for item in self.settings.phone_contact_seed:
                if await repository.find_contact_by_phone(session, item["phone_number"]):
                    continue
                await repository.create_contact(
                    session, item["name"], _e164(item["phone_number"]), item.get("notes", "")
                )

    async def create_contact(self, name: str, phone_number: str, notes: str = "") -> dict:
        if not name.strip():
            raise ValueError("Contact name is required.")
        phone_number = _e164(phone_number)
        async with self.session_factory() as session:
            if await repository.find_contact_by_name(session, name):
                raise ValueError("A contact with this name already exists.")
            if await repository.find_contact_by_phone(session, phone_number):
                raise ValueError("A contact with this phone number already exists.")
            row = await repository.create_contact(session, name, phone_number, notes)
        return serialize_contact(row)

    async def list_contacts(self) -> list[dict]:
        async with self.session_factory() as session:
            return [serialize_contact(row) for row in await repository.list_contacts(session)]

    async def list_calls(self, limit: int = 50) -> list[dict]:
        async with self.session_factory() as session:
            return [serialize_call(row) for row in await repository.list_phone_calls(session, limit)]

    async def status(self) -> dict:
        public_url = await self._resolve_public_url() if self.settings.phone_mode == "live" else ""
        return {
            "mode": self.settings.phone_mode,
            "number_configured": bool(self.settings.vobiz_did),
            "public_url_configured": bool(public_url),
            "speech_to_text_configured": bool(self.settings.sarvam_api_key),
        }

    async def get_call(self, call_id: str) -> dict | None:
        async with self.session_factory() as session:
            row = await repository.get_phone_call(session, call_id)
            return serialize_call(row) if row else None

    async def start_call(
        self,
        *,
        contact_name: str,
        mission: str,
        questions: list[str] | None = None,
        session_id: str | None = None,
        task_id: str | None = None,
    ) -> dict:
        if not mission.strip():
            raise ValueError("A call mission is required.")
        async with self.session_factory() as session:
            contact = await repository.find_contact_by_name(session, contact_name)
            if contact is None:
                available = [row.name for row in await repository.list_contacts(session)]
                suffix = f" Available contacts: {', '.join(available)}." if available else " Add the contact in Calls first."
                raise ValueError(f"Contact {contact_name!r} was not found.{suffix}")
            row = await repository.create_phone_call(
                session,
                contact_id=contact.id,
                contact_name=contact.name,
                phone_number=contact.phone_number,
                mission=mission.strip(),
                questions=_question_rows(mission, questions),
                session_id=session_id,
                task_id=task_id,
            )

        await self._publish(EventType.PHONE_CALL_QUEUED, row)
        if self.settings.phone_mode == "mock":
            return {**serialize_call(row), "mock": True, "message": "Call queued in mock mode; configure Vobiz and PHONE_PUBLIC_URL for live dialing."}

        try:
            public_url = await self._resolve_public_url()
            if not public_url:
                raise RuntimeError(
                    "Vobiz is configured, but Griffin has no public webhook URL. "
                    "Set PHONE_PUBLIC_URL or start an HTTPS ngrok tunnel."
                )
            findings = {**(row.findings or {}), "_callback_base": public_url}
            async with self.session_factory() as session:
                row = await repository.update_phone_call(session, row.id, findings=findings)
            provider_id = await self._dial(row, public_url)
            async with self.session_factory() as session:
                row = await repository.update_phone_call(
                    session, row.id, status="ringing", provider_call_id=provider_id, started_at=_now()
                )
            await self._publish(EventType.PHONE_CALL_STARTED, row)
            return {**serialize_call(row), "mock": False}
        except Exception as exc:
            logger.exception("phone.dial_failed", extra={"call_id": row.id})
            async with self.session_factory() as session:
                row = await repository.update_phone_call(
                    session, row.id, status="failed", error=str(exc), ended_at=_now()
                )
            await self._publish(EventType.PHONE_CALL_FAILED, row)
            raise

    async def _dial(self, row, public_url: str) -> str | None:
        query = {"job_id": row.id}
        if token := self._webhook_token():
            query["token"] = token
        base = public_url.rstrip("/")
        answer_url = f"{base}/api/phone/webhooks/vobiz/answer?{urlencode(query)}"
        hangup_url = f"{base}/api/phone/webhooks/vobiz/hangup?{urlencode(query)}"
        recording_url = f"{base}/api/phone/webhooks/vobiz/recording?{urlencode(query)}"
        payload = {
            "from": self.settings.vobiz_did,
            "to": row.phone_number,
            "answer_url": answer_url,
            "recording_url": recording_url,
            "answer_method": "POST",
            "hangup_url": hangup_url,
            "hangup_method": "POST",
        }
        url = f"{self.settings.vobiz_base_url.rstrip('/')}/Account/{self.settings.vobiz_auth_id}/Call/"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                url,
                json=payload,
                auth=(self.settings.vobiz_auth_id, self.settings.vobiz_auth_token),
            )
            if response.is_error:
                detail = response.text.strip()[:500] or response.reason_phrase
                raise RuntimeError(f"Vobiz rejected the call ({response.status_code}): {detail}")
            data = response.json()
        return data.get("request_uuid") or data.get("call_uuid") or data.get("call_sid") or data.get("CallUUID")

    def verify_webhook(self, token: str | None) -> bool:
        expected = self._webhook_token()
        return not expected or (token is not None and hmac.compare_digest(token, expected))

    def _webhook_token(self) -> str:
        """Return a stable callback token without exposing the Vobiz credential.

        An explicit secret wins. Live installations that omit one still receive
        authenticated callback URLs derived one-way from their Vobiz credentials.
        """
        if self.settings.phone_webhook_secret:
            return self.settings.phone_webhook_secret
        if self.settings.vobiz_auth_id and self.settings.vobiz_auth_token:
            material = f"griffin-phone:{self.settings.vobiz_auth_id}:{self.settings.vobiz_auth_token}"
            return hashlib.sha256(material.encode("utf-8")).hexdigest()
        return ""

    async def answer(self, call_id: str, provider_call_id: str | None = None) -> str:
        async with self.session_factory() as session:
            row = await repository.get_phone_call(session, call_id)
            if row is None:
                raise ValueError("Call job not found.")
            row = await repository.update_phone_call(
                session,
                call_id,
                status="active",
                provider_call_id=provider_call_id or row.provider_call_id,
                answered_at=_now(),
            )
        greeting = (
            f"Hi {row.contact_name}, this is Griffin, an AI assistant calling on behalf of Austin. "
            f"I am calling to {row.mission.rstrip('.')}. This call may be transcribed so I can report the answer accurately. "
            "Is now a good time for a quick question?"
        )
        row = await self._append_turn(row.id, "assistant", greeting)
        findings = dict(row.findings or {})
        findings["phase"] = "permission"
        async with self.session_factory() as session:
            row = await repository.update_phone_call(session, row.id, findings=findings)
        await self._publish(EventType.PHONE_CALL_ANSWERED, row)
        return self._xml(greeting, self._record_url(row))

    async def recording(self, call_id: str, user_text: str | None, recording_url: str | None) -> str:
        row = await self._require_call(call_id)
        text = (user_text or "").strip()
        if not text and recording_url:
            text = await self._transcribe(recording_url)
        if not text:
            return self._xml("I did not catch that. Could you say it once more?", self._record_url(row))

        row = await self._append_turn(call_id, "user", text)
        findings = dict(row.findings or {})
        phase = findings.get("phase", "permission")
        questions = row.questions or []
        if phase == "permission":
            if re.search(r"\b(no|busy|later|not\s+now|stop|do\s+not\s+call)\b", text.lower()):
                reply = "Understood. I will let Austin know. Thank you and goodbye."
                row = await self._append_turn(call_id, "assistant", reply)
                await self._complete(row, findings, "The contact declined or was unavailable for the call.", "declined")
                return self._xml(reply, hangup=True)
            findings["phase"] = "questions"
            findings["question_index"] = 0
            async with self.session_factory() as session:
                row = await repository.update_phone_call(session, call_id, findings=findings)
            reply = questions[0]["question"]
            await self._append_turn(call_id, "assistant", reply)
            return self._xml(reply, self._record_url(row))

        index = int(findings.get("question_index", 0))
        if index < len(questions):
            question = questions[index]
            findings[question["id"]] = {"question": question["question"], "answer": text}
            index += 1
        findings["question_index"] = index
        async with self.session_factory() as session:
            row = await repository.update_phone_call(session, call_id, findings=findings)

        if index < len(questions):
            reply = questions[index]["question"]
            await self._append_turn(call_id, "assistant", reply)
            return self._xml(reply, self._record_url(row))

        summary = self._summary(row, findings)
        reply = "Thank you. I have everything I need and will report it back to Austin. Goodbye."
        await self._append_turn(call_id, "assistant", reply)
        row = await self._complete(row, findings, summary, "completed")
        return self._xml(reply, hangup=True)

    async def hangup(self, call_id: str, duration_seconds: int | None = None) -> None:
        row = await self._require_call(call_id)
        if row.status in ("completed", "declined", "failed", "cancelled"):
            if duration_seconds is not None:
                async with self.session_factory() as session:
                    await repository.update_phone_call(session, call_id, duration_seconds=duration_seconds)
            return
        findings = dict(row.findings or {})
        summary = self._summary(row, findings) if any(k.startswith("q") for k in findings) else "The call ended before Griffin collected the requested information."
        await self._complete(row, findings, summary, "incomplete", duration_seconds)

    async def cancel(self, call_id: str) -> dict:
        row = await self._require_call(call_id)
        if row.status in ("completed", "declined", "failed", "cancelled", "incomplete"):
            return serialize_call(row)
        if row.provider_call_id and self.settings.phone_mode == "live":
            url = f"{self.settings.vobiz_base_url.rstrip('/')}/Account/{self.settings.vobiz_auth_id}/Call/{row.provider_call_id}/"
            headers = {"X-Auth-ID": self.settings.vobiz_auth_id, "X-Auth-Token": self.settings.vobiz_auth_token}
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.delete(url, headers=headers)
                response.raise_for_status()
        async with self.session_factory() as session:
            row = await repository.update_phone_call(session, call_id, status="cancelled", ended_at=_now())
        await self._publish(EventType.PHONE_CALL_COMPLETED, row)
        return serialize_call(row)

    async def _require_call(self, call_id: str):
        async with self.session_factory() as session:
            row = await repository.get_phone_call(session, call_id)
        if row is None:
            raise ValueError("Call job not found.")
        return row

    async def _append_turn(self, call_id: str, speaker: str, text: str):
        row = await self._require_call(call_id)
        transcript = list(row.transcript or [])
        turn = {"speaker": speaker, "text": text, "timestamp": _now().isoformat().replace("+00:00", "Z")}
        transcript.append(turn)
        async with self.session_factory() as session:
            row = await repository.update_phone_call(session, call_id, transcript=transcript)
        await self._publish(EventType.PHONE_CALL_TRANSCRIPT, row, {"turn": turn})
        return row

    async def _complete(self, row, findings: dict, summary: str, status: str, duration: int | None = None):
        findings = {key: value for key, value in findings.items() if key not in ("phase", "question_index") and not key.startswith("_")}
        report = f"Phone mission with {row.contact_name}: {summary}"
        assistant_message = None
        async with self.session_factory() as session:
            row = await repository.update_phone_call(
                session,
                row.id,
                status=status,
                findings=findings,
                summary=summary,
                duration_seconds=duration if duration is not None else row.duration_seconds,
                ended_at=_now(),
            )
            if row.session_id:
                assistant_message = await repository.add_message(
                    session,
                    row.session_id,
                    "assistant",
                    report,
                    tool_name="phone.call_contact",
                )
        await self._publish(EventType.PHONE_CALL_COMPLETED, row)
        if assistant_message is not None:
            await self.bus.publish(
                new_event(
                    EventType.AGENT_RESPONSE,
                    session_id=row.session_id,
                    task_id=row.task_id,
                    data={"message_id": assistant_message.id, "response": report},
                )
            )
        return row

    def _summary(self, row, findings: dict) -> str:
        answers = [value for key, value in findings.items() if key.startswith("q") and isinstance(value, dict)]
        if not answers:
            return "No requested answers were collected."
        joined = " ".join(f"{item.get('question', 'Question')} — {item.get('answer', 'No answer')}" for item in answers)
        return f"{row.contact_name} reported: {joined}"

    async def _publish(self, event_type: str, row, extra: dict | None = None) -> None:
        data = {"call": serialize_call(row), **(extra or {})}
        await self.bus.publish(
            new_event(event_type, session_id=row.session_id, task_id=row.task_id, data=data)
        )

    def _record_url(self, row) -> str:
        query = {"job_id": row.id}
        if token := self._webhook_token():
            query["token"] = token
        base = str((row.findings or {}).get("_callback_base") or self.settings.phone_public_url).rstrip("/")
        return f"{base}/api/phone/webhooks/vobiz/recording?{urlencode(query)}"

    async def _resolve_public_url(self) -> str:
        if self.settings.phone_public_url.strip():
            return self.settings.phone_public_url.strip().rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                response = await client.get("http://127.0.0.1:4040/api/tunnels")
                response.raise_for_status()
            for tunnel in response.json().get("tunnels", []):
                public_url = str(tunnel.get("public_url", ""))
                if public_url.startswith("https://"):
                    return public_url.rstrip("/")
        except Exception:
            pass
        return ""

    def _xml(self, text: str = "", record_url: str = "", hangup: bool = False) -> str:
        parts = ['<?xml version="1.0" encoding="UTF-8"?>', "<Response>"]
        if text:
            language = html.escape(self.settings.phone_language, quote=True)
            voice = html.escape(self.settings.phone_voice, quote=True)
            parts.append(f'<Speak language="{language}" voice="{voice}">{html.escape(text)}</Speak>')
        if record_url and not hangup:
            parts.append(f'<Record action="{html.escape(record_url, quote=True)}" method="POST" maxLength="25" timeout="3" playBeep="false" />')
        if hangup:
            parts.append("<Hangup/>")
        parts.append("</Response>")
        return "\n".join(parts)

    async def _transcribe(self, audio_url: str) -> str:
        if not self.settings.sarvam_api_key:
            return ""
        download_headers = {}
        if "vobiz" in audio_url.lower():
            download_headers = {"X-Auth-ID": self.settings.vobiz_auth_id, "X-Auth-Token": self.settings.vobiz_auth_token}
        async with httpx.AsyncClient(timeout=15) as client:
            audio = await client.get(audio_url, headers=download_headers)
            audio.raise_for_status()
            response = await client.post(
                f"{self.settings.sarvam_base_url.rstrip('/')}/speech-to-text",
                headers={"api-subscription-key": self.settings.sarvam_api_key},
                files={"file": ("recording.wav", audio.content, "audio/wav")},
                data={"model": "saarika:v2.5", "language_code": self.settings.phone_language},
            )
            response.raise_for_status()
        value = response.json().get("transcript", "")
        if isinstance(value, list):
            return " ".join(str(item.get("text", "")) for item in value if isinstance(item, dict)).strip()
        return str(value).strip()
