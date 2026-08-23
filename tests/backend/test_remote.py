"""Remote session pairing and authorization tests."""

from backend.remote.service import RemoteControlService
from backend.remote.macos import MacRemoteAdapter


class FakeAdapter:
    supported = True

    def __init__(self):
        self.actions = []
        self.opened_apps = []
        self.settings_opened = False

    def permissions(self):
        return {"screen_recording": True, "accessibility": True}

    async def capture_frame(self):
        return b"fake-jpeg"

    async def perform(self, action):
        self.actions.append(action)

    async def open_application(self, names):
        self.opened_apps.append(names)
        return names[0]

    async def open_hermes_agent(self):
        self.opened_apps.append(("hermes-cli",))
        return "Hermes Agent"

    def permission_target(self):
        return "/test/python3"

    async def open_accessibility_settings(self):
        self.settings_opened = True
        return self.permission_target()


def test_retina_pointer_mapping_uses_logical_display_bounds():
    adapter = MacRemoteAdapter()
    adapter.CGPoint = lambda x, y: type("Point", (), {"x": x, "y": y})()
    adapter.display_bounds = lambda: (0.0, 0.0, 1440.0, 900.0)

    point = adapter._point(0.5, 0.25)

    assert point.x == 720
    assert point.y == 225


async def test_native_text_posts_complete_unicode_key_pair():
    class FakeCoreGraphics:
        def __init__(self):
            self.keyboard_events = []
            self.unicode_events = []
            self.posted = []

        def CGEventCreateKeyboardEvent(self, _source, _key, down):
            event = 101 if down else 102
            self.keyboard_events.append(bool(down))
            return event

        def CGEventKeyboardSetUnicodeString(self, event, length, _units):
            self.unicode_events.append((event, length))

        def CGEventPost(self, tap, event):
            self.posted.append((tap, event))

    class FakeCoreFoundation:
        def CFRelease(self, _event):
            pass

    adapter = MacRemoteAdapter()
    adapter.supported = True
    adapter._cg = FakeCoreGraphics()
    adapter._cf = FakeCoreFoundation()
    adapter.permissions = lambda: {"screen_recording": True, "accessibility": True}

    await adapter.perform({"type": "text", "text": "Hello 👋"})

    assert adapter._cg.keyboard_events == [True, False]
    assert adapter._cg.unicode_events == [(101, 8), (102, 8)]
    assert adapter._cg.posted == [(0, 101), (0, 102)]


async def test_native_scroll_uses_pixel_units_and_both_axes():
    class FakeCoreGraphics:
        def __init__(self):
            self.scroll_args = None
            self.fields = []
            self.posted = []

        def CGEventCreateScrollWheelEvent2(self, *args):
            self.scroll_args = args
            return 201

        def CGEventSetIntegerValueField(self, event, field, value):
            self.fields.append((event, field, value))

        def CGEventPost(self, tap, event):
            self.posted.append((tap, event))

    class FakeCoreFoundation:
        def CFRelease(self, _event):
            pass

    adapter = MacRemoteAdapter()
    adapter.supported = True
    adapter._cg = FakeCoreGraphics()
    adapter._cf = FakeCoreFoundation()
    adapter.permissions = lambda: {"screen_recording": True, "accessibility": True}

    await adapter.perform({"type": "scroll", "dx": -7, "dy": 42})

    assert adapter._cg.scroll_args == (None, 0, 2, 42, -7, 0)
    assert adapter._cg.fields == [(201, 88, 1)]
    assert adapter._cg.posted == [(0, 201)]


async def test_remote_pair_input_frame_and_stop(client, app):
    adapter = FakeAdapter()
    app.state.griffin.remote = RemoteControlService(adapter=adapter)

    status = (await client.get("/api/remote")).json()
    assert status["state"] == "idle"
    assert status["ready"] is True
    assert status["can_start"] is True
    assert "lan_address" in status

    started = (await client.post("/api/remote/session")).json()
    assert started["state"] == "pairing"
    assert len(started["pairing_code"]) == 6

    rejected = await client.post("/api/remote/pair", json={"code": "000000"})
    assert rejected.status_code == 401

    paired = (await client.post("/api/remote/pair", json={"code": started["pairing_code"]})).json()
    token = paired["token"]
    assert paired["state"] == "paired"

    unauthorized = await client.post("/api/remote/input", json={"type": "tap", "x": 0.5, "y": 0.5})
    assert unauthorized.status_code == 401

    headers = {"Authorization": f"Bearer {token}"}
    settings = await client.post("/api/remote/permissions/accessibility", headers=headers)
    assert settings.json() == {"opened": True, "permission_target": "/test/python3"}
    assert adapter.settings_opened is True

    accepted = await client.post("/api/remote/input", headers=headers, json={"type": "tap", "x": 0.5, "y": 0.25})
    assert accepted.json() == {"accepted": True}
    assert adapter.actions == [{"type": "tap", "x": 0.5, "y": 0.25, "dx": 0, "dy": 0, "modifiers": []}]

    entered_fullscreen = await client.post("/api/remote/input", headers=headers, json={"type": "enter_fullscreen"})
    exited_fullscreen = await client.post("/api/remote/input", headers=headers, json={"type": "exit_fullscreen"})
    assert entered_fullscreen.json() == {"accepted": True}
    assert exited_fullscreen.json() == {"accepted": True}
    assert adapter.actions[-2:] == [
        {"type": "enter_fullscreen", "dx": 0, "dy": 0, "modifiers": []},
        {"type": "exit_fullscreen", "dx": 0, "dy": 0, "modifiers": []},
    ]

    frame = await client.get("/api/remote/frame", headers=headers)
    assert frame.status_code == 200
    assert frame.content == b"fake-jpeg"
    assert frame.headers["content-type"] == "image/jpeg"

    launched = await client.post("/api/remote/app", headers=headers, json={"app": "vscode"})
    assert launched.status_code == 200
    assert launched.json() == {
        "opened": True,
        "app": "vscode",
        "application": "Visual Studio Code",
    }
    assert adapter.opened_apps == [("Visual Studio Code",)]

    hermes = await client.post("/api/remote/app", headers=headers, json={"app": "hermes"})
    assert hermes.status_code == 200
    assert hermes.json()["application"] == "Hermes Agent"
    assert adapter.opened_apps[-1] == ("hermes-cli",)

    invalid_app = await client.post("/api/remote/app", headers=headers, json={"app": "calculator"})
    assert invalid_app.status_code == 422

    stopped = await client.delete("/api/remote/session", headers=headers)
    assert stopped.json() == {"stopped": True}
    assert (await client.get("/api/remote")).json()["state"] == "idle"


async def test_remote_rejects_incomplete_input(client, app):
    app.state.griffin.remote = RemoteControlService(adapter=FakeAdapter())
    started = (await client.post("/api/remote/session")).json()
    paired = (await client.post("/api/remote/pair", json={"code": started["pairing_code"]})).json()
    response = await client.post(
        "/api/remote/input",
        headers={"Authorization": f"Bearer {paired['token']}"},
        json={"type": "tap", "x": 0.5},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "REMOTE_INPUT_FAILED"
