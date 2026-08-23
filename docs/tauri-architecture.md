# Griffin desktop architecture

Griffin's Tauri 2 port preserves the existing application boundaries:

- React remains the dashboard, chat, avatar, voice, and remote-control UI.
- FastAPI remains the Griffin Kernel: orchestration, memory, models, workflows, and tools.
- Rust owns the desktop window, process lifecycle, tray, native IPC, and narrowly scoped OS capabilities.

Browser and phone access still use HTTP/WebSocket on the LAN. Tauri IPC is available only to the bundled `main` webview and is not routed through FastAPI, so a paired phone cannot invoke native desktop commands.

## Runtime lifecycle

At launch, Rust probes `http://127.0.0.1:8000/api/health` and verifies both `status=ok` and `service=griffin`. A matching existing kernel is reused and is never killed by Griffin. Otherwise:

- `tauri dev` launches `.venv/bin/python -m backend.desktop_entry`.
- a release build launches the architecture-suffixed `griffin-kernel` PyInstaller sidecar.

The owned PID and process handle stay in Rust. Readiness is bounded to 10 seconds. Process exit changes the runtime to `failed`; the System Status card and tray expose controlled restart. Restart and app shutdown terminate only the recorded child. There is no automatic rapid restart loop.

Runtime phases are `starting`, `ready`, `degraded`, `disconnected`, `restarting`, and `failed`. Rust emits `griffin://runtime-state`; the React provider combines that state with existing HTTP health and WebSocket connection state.

Desktop SQLite data is stored in Tauri's per-user app-data directory. Browser development retains the existing repository-relative configuration.

## Native trust boundary

The main-window capability grants only core event and window APIs. Shell, filesystem, process, notification, and opener plugins are not exposed to frontend JavaScript. Rust itself implements these validated commands:

- `runtime_status`
- `restart_backend`
- `get_platform_info`
- `show_notification` (bounded title/body)
- `open_url` (HTTP/HTTPS only, with length and host validation)

There is no arbitrary shell, executable path, or filesystem-path command. Native operations requested by agents should eventually use a local authenticated adapter between the Python semantic tool registry and these Tauri commands. That bridge is deliberately deferred until a transport can preserve the local-desktop trust boundary; existing LAN endpoints must never proxy Tauri IPC.

## Development and builds

Prerequisites are Node.js, Rust, Python 3.11+, and the platform requirements listed by Tauri. The current packaging target is Apple Silicon macOS.

```bash
# Existing browser/LAN stack
./scripts/dev.sh

# Backend or frontend independently
.venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
npm --prefix frontend run dev -- --host 0.0.0.0 --port 5173

# Tauri desktop development (starts its own backend if needed)
npm --prefix frontend run desktop:dev

# Sidecar only
.venv/bin/python -m pip install -r backend/requirements-desktop.txt
./scripts/build-sidecar.sh

# Griffin.app and DMG
npm --prefix frontend run desktop:build
```

`scripts/build-sidecar.sh` derives the Rust host triple and writes `frontend/src-tauri/binaries/griffin-kernel-<target-triple>`. The Tauri build runs this step before compiling the application and fails with an actionable message when PyInstaller or the virtual environment is missing.

Playwright's Python package is bundled, but Chromium remains an external browser payload. Install it in the environment used by Griffin (`playwright install chromium`) when real browser automation is required. Faster Whisper model files are still downloaded/managed by its existing local provider and are not embedded as static model assets.

Release signing and notarization are intentionally not configured. A distribution pipeline should add an Apple Developer ID certificate, hardened runtime/entitlements review, notarization, and stapling after the app and sidecar identities are finalized.

## Manual acceptance

1. Run `npm --prefix frontend run desktop:dev`; confirm a native window opens and chat reaches the automatically managed kernel.
2. Confirm System Status reports `ready` and the tray contains Open, Restart Kernel, and Quit.
3. Stop the owned kernel PID; confirm the UI reports failure, then use Restart Kernel.
4. Invoke `show_notification` and verify macOS notification permission/behavior. Invalid or oversized arguments must be rejected.
5. Run `./scripts/dev.sh` and connect from another LAN device to confirm browser/phone behavior remains intact.
6. Run `npm --prefix frontend run desktop:build`; launch the resulting `Griffin.app` without starting Python manually.
