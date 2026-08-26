from __future__ import annotations

import pytest

from backend.events.bus import EventBus
from backend.events.websocket_manager import WebSocketManager
from backend.tools.whatsapp.exceptions import WhatsAppApprovalInvalid, WhatsAppSendUncertain
from backend.tools.whatsapp.service import WhatsAppService


class FakeController:
    def __init__(self, matches=None, uncertain=False):
        self.matches = matches or [{"display_name": "Test Contact", "secondary_text": None, "confidence": 1.0}]
        self.uncertain = uncertain
        self.sends = []

    async def open(self):
        return {"status": "authenticated", "provider": "whatsapp_web", "ready": True}

    async def status(self):
        return await self.open()

    async def search_contact(self, query):
        return self.matches

    async def send_message(self, recipient, message):
        self.sends.append((recipient, message))
        if self.uncertain:
            raise WhatsAppSendUncertain("verification failed")


def service(settings, db, controller):
    bus = EventBus(db.session_factory, WebSocketManager())
    return WhatsAppService(settings, db.session_factory, bus, controller)


@pytest.mark.asyncio
async def test_prepare_approve_send_is_idempotent(settings, db):
    controller = FakeController()
    whatsapp = service(settings, db, controller)
    draft = await whatsapp.prepare_message("Test Contact", " hello from Griffin ")
    assert draft["status"] == "approval_required"
    assert draft["message"] == "hello from Griffin"

    approved = await whatsapp.approve(draft["action_id"])
    sent = await whatsapp.send(draft["action_id"], approved["approval_token"])
    repeated = await whatsapp.send(draft["action_id"], "ignored-after-success")

    assert sent == repeated
    assert controller.sends == [("Test Contact", "hello from Griffin")]


@pytest.mark.asyncio
async def test_wrong_token_and_cancelled_action_fail_closed(settings, db):
    whatsapp = service(settings, db, FakeController())
    draft = await whatsapp.prepare_message("Test Contact", "hello")
    await whatsapp.approve(draft["action_id"])
    with pytest.raises(WhatsAppApprovalInvalid):
        await whatsapp.send(draft["action_id"], "wrong")

    other = await whatsapp.prepare_message("Test Contact", "goodbye")
    await whatsapp.cancel(other["action_id"])
    with pytest.raises(WhatsAppApprovalInvalid):
        await whatsapp.approve(other["action_id"])


@pytest.mark.asyncio
async def test_uncertain_send_never_retries(settings, db):
    controller = FakeController(uncertain=True)
    whatsapp = service(settings, db, controller)
    draft = await whatsapp.prepare_message("Test Contact", "hello")
    approved = await whatsapp.approve(draft["action_id"])
    with pytest.raises(WhatsAppSendUncertain):
        await whatsapp.send(draft["action_id"], approved["approval_token"])
    with pytest.raises(WhatsAppApprovalInvalid):
        await whatsapp.send(draft["action_id"], approved["approval_token"])
    assert len(controller.sends) == 1


@pytest.mark.asyncio
async def test_api_lists_actions_without_starting_browser(client):
    response = await client.get("/api/tools/whatsapp/actions")
    assert response.status_code == 200
    assert response.json() == []
