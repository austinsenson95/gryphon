"""Event model + event bus tests."""

from sqlalchemy import select

from backend.memory import retrieval as repository
from backend.memory.models import Event
from backend.events.events import EventEnvelope, EventType, envelope_from_row, new_event


def test_event_envelope_shape():
    event = new_event(
        EventType.TOOL_CALL_STARTED,
        session_id="ses_1",
        task_id="task_1",
        run_id="run_1",
        data={"tool": "x"},
    )
    payload = event.model_dump()
    assert set(payload) == {"id", "type", "timestamp", "session_id", "task_id", "run_id", "data"}
    assert payload["id"].startswith("evt_")
    assert payload["type"] == "TOOL_CALL_STARTED"
    assert payload["timestamp"].endswith("Z")
    assert payload["session_id"] == "ses_1"
    assert payload["task_id"] == "task_1"
    assert payload["run_id"] == "run_1"
    assert payload["data"] == {"tool": "x"}


def test_event_envelope_nullable_fields():
    event = new_event(EventType.SESSION_CREATED, session_id="ses_1")
    assert event.task_id is None
    assert event.data == {}


def test_all_spec_event_types_defined():
    expected = {
        "SESSION_CREATED", "MESSAGE_RECEIVED", "AGENT_STARTED", "AGENT_THINKING",
        "TOOL_CALL_STARTED", "TOOL_CALL_COMPLETED", "TOOL_CALL_FAILED",
        "AGENT_RESPONSE", "TASK_STARTED", "TASK_COMPLETED", "TASK_FAILED",
        "USER_APPROVAL_REQUIRED",
        "STT_STARTED", "STT_COMPLETED", "STT_FAILED",
        "WORKFLOW_STARTED", "WORKFLOW_COMPLETED",
        # Phase 1 additions
        "PERMISSION_REQUIRED", "PERMISSION_GRANTED", "PERMISSION_DENIED",
        "BROWSER_NAVIGATION", "BROWSER_PAGE_LOADED",
        "PHONE_CALL_QUEUED", "PHONE_CALL_STARTED", "PHONE_CALL_ANSWERED",
        "PHONE_CALL_TRANSCRIPT", "PHONE_CALL_COMPLETED", "PHONE_CALL_FAILED",
        "WHATSAPP_ACTION_UPDATED",
    }
    assert set(EventType.ALL) == expected


async def test_bus_publish_notifies_subscriber(bus):
    received: list[EventEnvelope] = []
    bus.subscribe(received.append)
    event = await bus.publish(new_event(EventType.MESSAGE_RECEIVED, session_id="ses_x"))
    assert received == [event]


async def test_bus_publish_persists_to_db(bus, db):
    event = await bus.publish(
        new_event(EventType.TOOL_CALL_COMPLETED, session_id="ses_x", task_id="task_x", data={"k": "v"})
    )
    async with db.session_factory() as session:
        row = await session.get(Event, event.id)
        assert row is not None
        assert row.type == EventType.TOOL_CALL_COMPLETED
        assert row.session_id == "ses_x"
        assert row.task_id == "task_x"
        assert row.data == {"k": "v"}


async def test_bus_publish_ordering_preserved(bus, db):
    for idx in range(5):
        await bus.publish(new_event(EventType.AGENT_THINKING, session_id="s", data={"i": idx}))
    async with db.session_factory() as session:
        recent = await repository.get_recent_events(session, limit=5)
    assert [row.data["i"] for row in recent] == [0, 1, 2, 3, 4]


async def test_bus_async_subscriber(bus):
    seen: list[str] = []

    async def subscriber(event: EventEnvelope) -> None:
        seen.append(event.id)

    bus.subscribe(subscriber)
    event = await bus.publish(new_event(EventType.AGENT_STARTED))
    assert seen == [event.id]


async def test_envelope_from_row_roundtrip(bus, db):
    event = await bus.publish(new_event(EventType.TASK_STARTED, session_id="s", task_id="t", data={"a": 1}))
    async with db.session_factory() as session:
        row = (await session.scalars(select(Event).where(Event.id == event.id))).one()
    restored = envelope_from_row(row)
    assert restored.id == event.id
    assert restored.type == event.type
    assert restored.data == {"a": 1}
    assert restored.timestamp.endswith("Z")
