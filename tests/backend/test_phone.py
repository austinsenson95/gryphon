"""Outbound phone mission API, persistence, and webhook lifecycle."""

from __future__ import annotations

from backend.events.events import EventType
from backend.memory import retrieval as repository


async def test_contact_and_mock_call_job(client):
    created = await client.post(
        "/api/phone/contacts",
        json={"name": "Rahul", "phone_number": "+919876543210", "notes": "Friend"},
    )
    assert created.status_code == 201
    assert created.json()["name"] == "Rahul"
    assert created.json()["call_authorized"] is True
    assert created.json()["authorization_source"] == "saved_contact"

    response = await client.post(
        "/api/phone/calls",
        json={
            "contact_name": "Rahul",
            "mission": "learn his availability",
            "questions": ["Which weekend works?", "What time is best?"],
        },
    )
    assert response.status_code == 202
    call = response.json()
    assert call["status"] == "queued"
    assert call["mock"] is True
    assert call["questions"][0]["question"] == "Which weekend works?"

    calls = (await client.get("/api/phone/calls")).json()
    assert calls[0]["id"] == call["id"]


async def test_saving_indian_mobile_adds_it_to_call_allowlist(client):
    created = await client.post(
        "/api/phone/contacts",
        json={"name": "Anita", "phone_number": "98765 43210"},
    )

    assert created.status_code == 201
    assert created.json()["phone_number"] == "+919876543210"
    assert created.json()["call_authorized"] is True

    unsaved = await client.post(
        "/api/phone/calls",
        json={"contact_name": "Not saved", "mission": "ask a question"},
    )
    assert unsaved.status_code == 400
    assert "not found" in unsaved.json()["error"]["message"]


async def test_webhook_conversation_collects_findings(client, app):
    await client.post(
        "/api/phone/contacts",
        json={"name": "Maya", "phone_number": "+919111111111"},
    )
    queued = (
        await client.post(
            "/api/phone/calls",
            json={
                "contact_name": "Maya",
                "mission": "plan dinner",
                "questions": ["Which day works?", "Any food preference?"],
            },
        )
    ).json()
    call_id = queued["id"]

    answered = await client.post(
        f"/api/phone/webhooks/vobiz/answer?job_id={call_id}",
        json={"CallUUID": "provider-123"},
    )
    assert answered.status_code == 200
    assert "AI assistant" in answered.text
    assert '<Speak language="en-IN" voice="Polly.Aditi">' in answered.text
    assert "<Record" in answered.text

    consent = await client.post(
        f"/api/phone/webhooks/vobiz/recording?job_id={call_id}",
        json={"user_text": "Yes, now is fine"},
    )
    assert "Which day works?" in consent.text

    first = await client.post(
        f"/api/phone/webhooks/vobiz/recording?job_id={call_id}",
        json={"user_text": "Friday evening"},
    )
    assert "Any food preference?" in first.text

    final = await client.post(
        f"/api/phone/webhooks/vobiz/recording?job_id={call_id}",
        json={"user_text": "Vegetarian food"},
    )
    assert "<Hangup" in final.text

    call = (await client.get(f"/api/phone/calls/{call_id}")).json()
    assert call["status"] == "completed"
    assert call["findings"]["q1"]["answer"] == "Friday evening"
    assert call["findings"]["q2"]["answer"] == "Vegetarian food"
    assert "Friday evening" in call["summary"]
    assert len(call["transcript"]) == 7

    async with app.state.griffin.db.session_factory() as session:
        rows = await repository.get_recent_events(session, limit=100)
    types = [row.type for row in rows]
    assert EventType.PHONE_CALL_ANSWERED in types
    assert EventType.PHONE_CALL_TRANSCRIPT in types
    assert EventType.PHONE_CALL_COMPLETED in types


async def test_phone_tool_is_registered_with_confirmation(app):
    tool = app.state.griffin.registry.get("phone.call_contact")
    assert tool is not None
    assert tool.permission == "confirm"
    assert app.state.griffin.registry.get("phone.get_call_status").permission == "safe"


async def test_provider_rejection_is_reported_clearly(client, app, monkeypatch):
    async def reject(**_kwargs):
        raise RuntimeError("Vobiz rejected the call (402): Insufficient balance")

    monkeypatch.setattr(app.state.griffin.phone, "start_call", reject)
    response = await client.post(
        "/api/phone/calls",
        json={"contact_name": "Austin", "mission": "run a smoke test"},
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "PHONE_PROVIDER_REJECTED"
    assert "Insufficient balance" in response.json()["error"]["message"]


async def test_record_url_live_vobiz_field_is_forwarded(client, app, monkeypatch):
    observed = {}

    async def capture(call_id, user_text, recording_url):
        observed.update(call_id=call_id, user_text=user_text, recording_url=recording_url)
        return "<Response/>"

    monkeypatch.setattr(app.state.griffin.phone, "verify_webhook", lambda _token: True)
    monkeypatch.setattr(app.state.griffin.phone, "recording", capture)
    response = await client.post(
        "/api/phone/webhooks/vobiz/recording?job_id=live-test",
        data={"RecordUrl": "https://media.vobiz.ai/example.mp3"},
    )

    assert response.status_code == 200
    assert observed["recording_url"] == "https://media.vobiz.ai/example.mp3"
