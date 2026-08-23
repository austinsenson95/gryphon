"""Thin, dependency-free wrappers around macOS screen and input APIs."""

from __future__ import annotations

import asyncio
import ctypes
import shlex
import shutil
import sys
import tempfile
from pathlib import Path


class MacRemoteAdapter:
    """Capture the main display and inject input through CoreGraphics.

    Importing this class is safe on every platform. Native frameworks are
    loaded lazily so the backend and its test suite remain portable.
    """

    KEY_CODES = {
        "enter": 36, "return": 36, "tab": 48, "space": 49,
        "backspace": 51, "delete": 51, "escape": 53,
        "left": 123, "right": 124, "down": 125, "up": 126,
        "home": 115, "end": 119, "pageup": 116, "pagedown": 121,
    }
    MODIFIER_FLAGS = {
        "shift": 1 << 17,
        "control": 1 << 18,
        "option": 1 << 19,
        "alt": 1 << 19,
        "command": 1 << 20,
        "meta": 1 << 20,
    }

    def __init__(self) -> None:
        self.supported = sys.platform == "darwin"
        self._cg = None
        self._app_services = None
        self._cf = None

    def _load_frameworks(self) -> None:
        if not self.supported or self._cg is not None:
            return
        self._cg = ctypes.CDLL(
            "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
        )
        self._app_services = ctypes.CDLL(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
        )
        self._cf = ctypes.CDLL(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )

        class CGPoint(ctypes.Structure):
            _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

        class CGSize(ctypes.Structure):
            _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]

        class CGRect(ctypes.Structure):
            _fields_ = [("origin", CGPoint), ("size", CGSize)]

        self.CGPoint = CGPoint
        self.CGRect = CGRect
        self._cg.CGMainDisplayID.restype = ctypes.c_uint32
        self._cg.CGDisplayBounds.argtypes = [ctypes.c_uint32]
        self._cg.CGDisplayBounds.restype = CGRect
        self._cg.CGEventCreateMouseEvent.argtypes = [
            ctypes.c_void_p, ctypes.c_uint32, CGPoint, ctypes.c_uint32
        ]
        self._cg.CGEventCreateMouseEvent.restype = ctypes.c_void_p
        self._cg.CGEventCreateKeyboardEvent.argtypes = [
            ctypes.c_void_p, ctypes.c_uint16, ctypes.c_bool
        ]
        self._cg.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
        self._cg.CGEventKeyboardSetUnicodeString.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_uint16)
        ]
        self._cg.CGEventSetFlags.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
        self._cg.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
        self._cg.CGEventSetIntegerValueField.argtypes = [
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int64
        ]
        self._cf.CFRelease.argtypes = [ctypes.c_void_p]

    def permissions(self) -> dict[str, bool]:
        if not self.supported:
            return {"screen_recording": False, "accessibility": False}
        try:
            self._load_frameworks()
            self._cg.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
            self._app_services.AXIsProcessTrusted.restype = ctypes.c_bool
            return {
                "screen_recording": bool(self._cg.CGPreflightScreenCaptureAccess()),
                "accessibility": bool(self._app_services.AXIsProcessTrusted()),
            }
        except (AttributeError, OSError):
            return {"screen_recording": False, "accessibility": False}

    def display_bounds(self) -> tuple[float, float, float, float]:
        self._load_frameworks()
        display = self._cg.CGMainDisplayID()
        bounds = self._cg.CGDisplayBounds(display)
        result = (
            float(bounds.origin.x),
            float(bounds.origin.y),
            float(bounds.size.width),
            float(bounds.size.height),
        )
        if result[2] <= 0 or result[3] <= 0:
            raise RuntimeError("macOS did not report a usable main display.")
        return result

    def display_size(self) -> tuple[int, int]:
        _, _, width, height = self.display_bounds()
        return int(width), int(height)

    async def capture_frame(self) -> bytes:
        if not self.supported:
            raise RuntimeError("Screen sharing is only available on macOS.")
        capture = shutil.which("screencapture")
        if not capture:
            raise RuntimeError("macOS screen capture is unavailable.")
        with tempfile.TemporaryDirectory(prefix="gryphon-remote-") as temp_dir:
            destination = Path(temp_dir) / "frame.jpg"
            proc = await asyncio.create_subprocess_exec(
                capture, "-x", "-C", "-t", "jpg", str(destination),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
            if proc.returncode != 0 or not destination.exists():
                detail = stderr.decode(errors="replace").strip()
                raise RuntimeError(detail or "Could not capture the Mac screen.")
            # A Retina screenshot can be several megabytes. Keep the MVP's
            # polling stream light enough for a normal local Wi-Fi network.
            sips = shutil.which("sips")
            if sips:
                resize = await asyncio.create_subprocess_exec(
                    sips, "-Z", "1440", "-s", "formatOptions", "65", str(destination),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.wait_for(resize.communicate(), timeout=5)
            return destination.read_bytes()

    def _post(self, event: int) -> None:
        self._cg.CGEventPost(0, event)
        self._cf.CFRelease(event)

    def _point(self, x: float, y: float):
        origin_x, origin_y, width, height = self.display_bounds()
        return self.CGPoint(
            origin_x + max(0, min(1, x)) * width,
            origin_y + max(0, min(1, y)) * height,
        )

    def _mouse_event(self, event_type: int, point, button: int, click_count: int = 1) -> None:
        event = self._cg.CGEventCreateMouseEvent(None, event_type, point, button)
        self._cg.CGEventSetIntegerValueField(event, 1, click_count)
        self._post(event)

    async def perform(self, action: dict) -> None:
        if not self.supported:
            raise RuntimeError("Remote input is only available on macOS.")
        self._load_frameworks()
        kind = action["type"]
        if not self.permissions()["accessibility"]:
            raise RuntimeError(
                "Remote control needs Accessibility permission. Enable it for the app "
                "running Gryphon in System Settings → Privacy & Security → Accessibility."
            )
        if kind in {"move", "tap", "double_tap", "secondary_tap"}:
            point = self._point(float(action["x"]), float(action["y"]))
            self._mouse_event(5, point, 0)
            if kind == "tap":
                self._mouse_event(1, point, 0)
                self._mouse_event(2, point, 0)
            elif kind == "double_tap":
                self._mouse_event(1, point, 0, 1)
                self._mouse_event(2, point, 0, 1)
                await asyncio.sleep(0.06)
                self._mouse_event(1, point, 0, 2)
                self._mouse_event(2, point, 0, 2)
            elif kind == "secondary_tap":
                self._mouse_event(3, point, 1)
                self._mouse_event(4, point, 1)
            return
        if kind == "scroll":
            self._cg.CGEventCreateScrollWheelEvent.argtypes = [
                ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                ctypes.c_int32, ctypes.c_int32,
            ]
            self._cg.CGEventCreateScrollWheelEvent.restype = ctypes.c_void_p
            event = self._cg.CGEventCreateScrollWheelEvent(
                None, 1, 2, int(action.get("dy", 0)), int(action.get("dx", 0))
            )
            self._post(event)
            return
        if kind == "key":
            key = str(action["key"]).lower()
            if key not in self.KEY_CODES:
                raise ValueError(f"Unsupported key: {key}")
            flags = sum(self.MODIFIER_FLAGS.get(str(m).lower(), 0) for m in action.get("modifiers", []))
            for down in (True, False):
                event = self._cg.CGEventCreateKeyboardEvent(None, self.KEY_CODES[key], down)
                if flags:
                    self._cg.CGEventSetFlags(event, flags)
                self._post(event)
            return
        if kind == "text":
            for chunk_start in range(0, len(action["text"]), 20):
                chunk = action["text"][chunk_start:chunk_start + 20]
                encoded = chunk.encode("utf-16-le")
                units = (ctypes.c_uint16 * (len(encoded) // 2)).from_buffer_copy(encoded)
                event = self._cg.CGEventCreateKeyboardEvent(None, 0, True)
                self._cg.CGEventKeyboardSetUnicodeString(event, len(units), units)
                self._post(event)
            return
        raise ValueError(f"Unsupported remote action: {kind}")

    async def open_application(self, names: tuple[str, ...]) -> str:
        if not self.supported:
            raise RuntimeError("Application shortcuts are only available on macOS.")
        open_bin = shutil.which("open")
        if not open_bin:
            raise RuntimeError("The macOS application launcher is unavailable.")
        last_error = "Application not found."
        for name in names:
            proc = await asyncio.create_subprocess_exec(
                open_bin, "-a", name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=8)
            if proc.returncode == 0:
                return name
            last_error = stderr.decode(errors="replace").strip() or last_error
        raise RuntimeError(last_error)

    async def open_hermes_agent(self) -> str:
        """Start the installed Hermes CLI in a new Terminal session."""
        hermes_bin = shutil.which("hermes")
        osascript_bin = shutil.which("osascript")
        if not hermes_bin:
            # Some distributions provide a native app instead of the CLI.
            return await self.open_application(("Hermes", "Hermes Agent"))
        if not osascript_bin:
            raise RuntimeError("AppleScript is unavailable, so Hermes cannot open in Terminal.")
        shell_command = shlex.quote(hermes_bin)
        apple_command = shell_command.replace("\\", "\\\\").replace('"', '\\"')
        proc = await asyncio.create_subprocess_exec(
            osascript_bin,
            "-e", f'tell application "Terminal" to do script "{apple_command}"',
            "-e", 'tell application "Terminal" to activate',
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=8)
        if proc.returncode != 0:
            raise RuntimeError(
                stderr.decode(errors="replace").strip() or "Could not start Hermes."
            )
        return "Hermes Agent"
