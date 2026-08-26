"""Approval, idempotency and audit boundary for WhatsApp actions."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select

from backend.core.logging import get_logger
from backend.events.events import EventType, new_event
from backend.memory.models import ActionAudit, PendingAction
from backend.memory.retrieval import iso
from backend.tools.whatsapp.exceptions import (
    WhatsAppAmbiguousContact, WhatsAppApprovalInvalid, WhatsAppContactNotFound,
    WhatsAppDisabled, WhatsAppError, WhatsAppSendUncertain,
)

logger = get_logger("griffin.whatsapp")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_payload(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class WhatsAppService:
    def __init__(self, settings, session_factory, bus, controller) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.bus = bus
        self.controller = controller
        self._send_lock = asyncio.Lock()

    def _enabled(self) -> None:
        if not self.settings.griffin_whatsapp_enabled:
            raise WhatsAppDisabled("WhatsApp integration is disabled.")

    async def open(self) -> dict:
        self._enabled()
        return await self.controller.open()

    async def status(self) -> dict:
        if not self.settings.griffin_whatsapp_enabled:
            return {"status": "disabled", "provider": "whatsapp_web", "ready": False}
        return await self.controller.status()

    async def disconnect(self) -> dict:
        """Close the local browser only; linked-device state is preserved."""
        await self.controller.session.close()
        return {"status": "not_started", "provider": "whatsapp_web", "ready": False, "profile_preserved": True}

    async def search_contact(self, query: str) -> dict:
        self._enabled()
        query = query.strip()
        if not query:
            raise ValueError("Contact name cannot be empty.")
        return {"matches": await self.controller.search_contact(query)}

    async def prepare_message(self, recipient: str, message: str) -> dict:
        self._enabled()
        recipient, message = recipient.strip(), message.strip()
        if not recipient:
            raise ValueError("Recipient cannot be empty.")
        if not message:
            raise ValueError("Message cannot be empty.")
        if len(message) > self.settings.griffin_whatsapp_max_message_chars:
            raise ValueError(f"Message exceeds {self.settings.griffin_whatsapp_max_message_chars} characters.")
        matches = await self.controller.search_contact(recipient)
        exact = [m for m in matches if m["display_name"].casefold() == recipient.casefold()]
        if len(exact) != 1:
            if matches:
                raise WhatsAppAmbiguousContact("Multiple chats match this recipient: " + ", ".join(m["display_name"] for m in matches))
            raise WhatsAppContactNotFound(f"I couldn't find a WhatsApp chat matching '{recipient}'.")
        resolved = exact[0]["display_name"]
        payload = {"recipient": resolved, "message": message}
        action = PendingAction(
            id=f"wa_{uuid.uuid4().hex}", tool_name="whatsapp.send_message",
            action_type="send_message", payload=payload, payload_hash=_hash_payload(payload),
            status="pending", expires_at=_now() + timedelta(seconds=self.settings.griffin_whatsapp_approval_ttl_seconds),
        )
        async with self.session_factory() as db:
            db.add(action)
            await db.commit()
        result = self._public(action)
        await self._emit(action)
        logger.info("whatsapp.draft_prepared", extra={"action_id": action.id, "recipient": resolved, "message_hash": action.payload_hash})
        return result

    async def approve(self, action_id: str) -> dict:
        token = secrets.token_urlsafe(32)
        async with self.session_factory() as db:
            action = await db.get(PendingAction, action_id)
            self._require(action, {"pending"})
            if self._expired(action):
                action.status = "expired"
                await db.commit()
                await self._emit(action)
                raise WhatsAppApprovalInvalid("This WhatsApp draft has expired.")
            action.status, action.approved_at, action.token_hash = "approved", _now(), _token_hash(token)
            await db.commit()
            await db.refresh(action)
        await self._emit(action)
        return {**self._public(action), "approval_token": token}

    async def cancel(self, action_id: str) -> dict:
        async with self.session_factory() as db:
            action = await db.get(PendingAction, action_id)
            self._require(action, {"pending", "approved"})
            action.status = "cancelled"
            action.token_hash = None
            await db.commit()
            await db.refresh(action)
        await self._emit(action)
        return self._public(action)

    async def send(self, action_id: str, approval_token: str) -> dict:
        async with self._send_lock:
            async with self.session_factory() as db:
                action = await db.get(PendingAction, action_id)
                if action is None:
                    raise WhatsAppApprovalInvalid("WhatsApp draft not found.")
                if action.status == "sent":
                    return action.result or self._public(action)
                self._require(action, {"approved"})
                if self._expired(action) or not action.token_hash or not hmac.compare_digest(action.token_hash, _token_hash(approval_token)):
                    raise WhatsAppApprovalInvalid("Approval is invalid or expired.")
                if _hash_payload(action.payload) != action.payload_hash:
                    raise WhatsAppApprovalInvalid("The approved message no longer matches its draft.")
                action.status = "executing"
                await db.commit()
                await db.refresh(action)
            await self._emit(action)
            try:
                await self.controller.send_message(action.payload["recipient"], action.payload["message"])
            except WhatsAppSendUncertain:
                await self._finish(action.id, "uncertain", None)
                raise
            except Exception:
                await self._finish(action.id, "failed", None)
                raise
            result = {
                "status": "sent", "action_id": action.id,
                "recipient": action.payload["recipient"], "message": action.payload["message"],
                "sent_at": iso(_now()),
            }
            return await self._finish(action.id, "sent", result)

    async def _finish(self, action_id: str, status: str, result: dict | None) -> dict:
        async with self.session_factory() as db:
            action = await db.get(PendingAction, action_id)
            action.status, action.result = status, result
            if status == "sent":
                action.consumed_at = _now()
            audit = ActionAudit(
                id=f"audit_{uuid.uuid4().hex}", action_id=action.id, tool="whatsapp",
                action="send_message", recipient=action.payload["recipient"],
                message_hash=action.payload_hash, approved=action.approved_at is not None, result=status,
            )
            db.add(audit)
            await db.commit()
            await db.refresh(action)
        await self._emit(action)
        logger.info(f"whatsapp.send_{status}", extra={"action_id": action.id, "recipient": action.payload["recipient"], "message_hash": action.payload_hash})
        return result or self._public(action)

    async def list_actions(self, limit: int = 20) -> list[dict]:
        async with self.session_factory() as db:
            rows = list((await db.scalars(select(PendingAction).order_by(desc(PendingAction.created_at)).limit(limit))).all())
            changed = False
            for row in rows:
                if row.status in {"pending", "approved"} and self._expired(row):
                    row.status = "expired"
                    changed = True
            if changed:
                await db.commit()
            return [self._public(row) for row in rows]

    @staticmethod
    def _expired(action: PendingAction) -> bool:
        expires = action.expires_at.replace(tzinfo=timezone.utc) if action.expires_at.tzinfo is None else action.expires_at
        return expires <= _now()

    @staticmethod
    def _require(action, statuses: set[str]) -> None:
        if action is None or action.status not in statuses:
            raise WhatsAppApprovalInvalid("This WhatsApp action is no longer available.")

    @staticmethod
    def _public(action: PendingAction) -> dict:
        return {
            "status": "approval_required" if action.status == "pending" else action.status,
            "action_id": action.id, "recipient": action.payload["recipient"],
            "message": action.payload["message"], "message_hash": action.payload_hash,
            "expires_at": iso(action.expires_at), "created_at": iso(action.created_at),
            **({"sent_at": (action.result or {}).get("sent_at")} if action.status == "sent" else {}),
        }

    async def _emit(self, action: PendingAction) -> None:
        await self.bus.publish(new_event(EventType.WHATSAPP_ACTION_UPDATED, data={"action": self._public(action)}))
