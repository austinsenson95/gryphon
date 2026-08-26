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
