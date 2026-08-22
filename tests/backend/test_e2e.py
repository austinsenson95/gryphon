"""End-to-end API tests over HTTP + WebSocket."""

import asyncio
import json

import websockets

from backend.events.events import EventType


async def test_chat_creates_session_and_responds(client):
    response = await client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"]
    assert body["message_id"]
    assert body["task_id"]
    assert "Gryphon" in body["response"]
    assert body["tool_calls"] == []

    events = await client.get("/api/events", params={"limit": 50})
    types = [e["type"] for e in events.json()]
    assert types[0] == EventType.SESSION_CREATED
    assert EventType.MESSAGE_RECEIVED in types


async def test_chat_validation_error_envelope(client):
    response = await client.post("/api/chat", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"


async def test_chat_reuses_existing_session(client):
    first = (await client.post("/api/chat", json={"message": "hi"})).json()
    second = (
        await client.post(
            "/api/chat", json={"message": "hi again", "session_id": first["session_id"]}
        )
    ).json()
    assert second["session_id"] == first["session_id"]


async def test_e2e_time_question_lifecycle(client):
    """The flagship Phase 0 flow: full event lifecycle for 'What time is it?'"""
    response = await client.post("/api/chat", json={"message": "What time is it?"})
    assert response.status_code == 200
    body = response.json()

    # Response mentions the time and really came through system.get_time.
    assert "time" in body["response"].lower()
    assert body["tool_calls"][0]["tool"] == "system.get_time"
    assert body["tool_calls"][0]["success"] is True
    assert body["tool_calls"][0]["data"]["unix"] > 0

    # All lifecycle events persisted, in order.
    events = (await client.get("/api/events", params={"limit": 50})).json()
    types = [e["type"] for e in events]
    expected_order = [
        EventType.MESSAGE_RECEIVED,
        EventType.TASK_STARTED,
        EventType.AGENT_STARTED,
        EventType.AGENT_THINKING,
        EventType.TOOL_CALL_STARTED,
        EventType.TOOL_CALL_COMPLETED,
        EventType.AGENT_RESPONSE,
        EventType.TASK_COMPLETED,
    ]
    positions = []
    for expected in expected_order:
        assert expected in types, f"missing event {expected}"
        positions.append(types.index(expected))
    assert positions == sorted(positions), f"events out of order: {types}"
    assert types.index(EventType.TASK_STARTED) == types.index(EventType.MESSAGE_RECEIVED) + 1

    # Every event carries the contract envelope fields.
    for event in events:
        assert event["id"].startswith("evt_")
        assert event["timestamp"].endswith("Z")
        assert event["session_id"] == body["session_id"]
        assert isinstance(event["data"], dict)

    # Task row completed, with its tool call attached.
    task_response = await client.get(f"/api/tasks/{body['task_id']}")
    assert task_response.status_code == 200
    task_body = task_response.json()
    assert task_body["task"]["status"] == "completed"
    assert task_body["task"]["completed_at"] is not None
    assert len(task_body["tool_calls"]) == 1
    assert task_body["tool_calls"][0]["tool"] == "system.get_time"


async def test_get_task_not_found(client):
    response = await client.get("/api/tasks/task_missing")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "TASK_NOT_FOUND"


async def test_websocket_hello_and_live_events(app):
    # Pre-seed one event so the replay path is exercised too.
    state = app.state.gryphon
    from backend.events.events import new_event

    await state.bus.publish(new_event(EventType.SESSION_CREATED, session_id="ses_seed"))

    transport_port = None
    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)

    async def run_server():
        await server.serve()

    task = asyncio.create_task(run_server())
    try:
        for _ in range(50):
            await asyncio.sleep(0.1)
            if server.started:
                break
        transport_port = server.servers[0].sockets[0].getsockname()[1]

        async with websockets.connect(f"ws://127.0.0.1:{transport_port}/ws") as ws:
            hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            assert hello["type"] == "CONNECTED"
            replay = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            assert replay["type"] == EventType.SESSION_CREATED
            assert replay["session_id"] == "ses_seed"
    finally:
        server.should_exit = True
        await task
