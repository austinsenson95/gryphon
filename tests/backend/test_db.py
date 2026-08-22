"""DB persistence round-trip tests."""

from backend.memory import retrieval as repository


async def test_session_message_task_event_roundtrip(db):
    async with db.session_factory() as session:
        ses = await repository.create_session(session, title="Chat")
        msg = await repository.add_message(session, ses.id, "user", "hello")
        task = await repository.create_task(session, ses.id, "hello")
        evt = await repository.add_event(session, "evt_test1", "MESSAGE_RECEIVED", ses.id, None, {"m": msg.id})
        call = await repository.add_tool_call(session, task.id, "system.get_time", {}, {"iso": "x"}, True)
        ntf = await repository.add_notification(session, "info", "title", "body")

        assert (await repository.get_session(session, ses.id)).title == "Chat"
        messages = await repository.get_recent_messages(session, ses.id, limit=20)
        assert [m.content for m in messages] == ["hello"]

        await repository.set_task_status(session, task.id, "completed", result="done", completed=True)
        updated = await repository.get_task(session, task.id)
        assert updated.status == "completed"
        assert updated.result == "done"
        assert updated.completed_at is not None

        events = await repository.get_recent_events(session, limit=10)
        assert [e.id for e in events] == ["evt_test1"]
        assert evt.type == "MESSAGE_RECEIVED"

        calls = await repository.get_tool_calls_for_task(session, task.id)
        assert calls[0].id == call.id
        assert calls[0].tool == "system.get_time"
        assert calls[0].success is True

        unread = await repository.get_unread_notifications(session)
        assert [n.id for n in unread] == [ntf.id]


async def test_recent_messages_limit_and_order(db):
    async with db.session_factory() as session:
        ses = await repository.create_session(session, title="t")
        for i in range(25):
            await repository.add_message(session, ses.id, "user", f"msg {i}")
        recent = await repository.get_recent_messages(session, ses.id, limit=20)
    assert len(recent) == 20
    assert recent[0].content == "msg 5"
    assert recent[-1].content == "msg 24"


async def test_messages_support_tool_role(db):
    async with db.session_factory() as session:
        ses = await repository.create_session(session, title="t")
        await repository.add_message(session, ses.id, "user", "time?")
        await repository.add_message(session, ses.id, "tool", '{"ok": true}', tool_name="system.get_time")
        await repository.add_message(session, ses.id, "assistant", "It is noon.")
        messages = await repository.get_recent_messages(session, ses.id)
    assert [m.role for m in messages] == ["user", "tool", "assistant"]
    assert messages[1].tool_name == "system.get_time"
