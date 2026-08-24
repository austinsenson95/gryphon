# Griffin — Phase 1

Desktop/Tauri development and packaging are documented in
[`docs/tauri-architecture.md`](docs/tauri-architecture.md).

A **local-first personal AI assistant**. Your Mac (or any machine) is the server; the web dashboard is Griffin's world — a draggable avatar, live activity feed, chat with **voice input**, task state, and tool activity, all streaming over WebSocket.

Phase 1 connects the dashboard to a real agentic execution loop:

```text
TEXT / VOICE → LOCAL STT → AGENT RUNTIME → LOCAL LLM (Ollama)
      → STRUCTURED TOOL PLAN → VALIDATOR (command registry boundary)
      → PYTHON EXECUTOR → macOS (apps / browser / folders / projects)
      → LIVE EVENTS → DASHBOARD
```

The LLM only *proposes* structured tool calls. Python validates every call against the registered command catalog (allowlisted apps, allowlisted directories, validated URLs) and executes through safe native mechanisms (`asyncio.create_subprocess_exec` with argv lists — no shell, no `eval`, ever). Unknown commands, unknown workflows, invalid URLs, disallowed paths and privileged tools all **fail closed** with structured errors.

![Griffin dashboard](docs/dashboard.png)

Phase 0 is the minimum viable skeleton, built as a **modular monolith**: one FastAPI backend, one React frontend, SQLite persistence. Everything is designed so future capabilities (browser automation, messaging, memory, voice, multi-agent) plug in without rewriting the core.

## 1. Architecture

```text
USER → WEB APP → GRIFFIN API → AGENT/LLM → TOOL REGISTRY → TOOL EXECUTION
                                      ↓
                                 EVENT BUS  ──→ SQLite (persisted)
                                      ↓
                             WEBSOCKET → DASHBOARD + AVATAR
```

- **Backend** (`backend/`, Python 3.11+ / FastAPI) — REST + WebSocket, agent runtime, LLM provider abstraction, tool registry with permission levels, event bus, SQLite via SQLAlchemy async.
- **Frontend** (`frontend/`, Vite + React 18 + TypeScript + Tailwind) — glassmorphism dashboard built on a presentational `GlassCard` primitive; event-driven state (no polling); draggable avatar with a 7-state machine driven by backend events.
- **Contracts** — the agent never knows which LLM provider or which tools exist; both come from abstractions (`llm/base.py`, `tools/registry.py`). Adding a provider or a tool never touches the agent loop.

See `SPEC.md` (build contract) and `docs/phase-0.md` (design notes).

## 2. Installation

Requirements: Python 3.11+, Node 20+, npm 10+.

```bash
./scripts/setup.sh        # or: make setup
```

This creates `backend/.venv`, installs backend + frontend dependencies, and creates `backend/.env` from the example.

## 3. Environment setup

All configuration lives in `backend/.env` (never committed; `backend/.env.example` is the template):

| Variable | Default | Purpose |
|---|---|---|
| `APP_NAME` / `ENVIRONMENT` | `Griffin` / `development` | service identity |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | bind address (LAN-accessible) |
| `LLM_PROVIDER` | `ollama` | `ollama` (local, default) or `openai_compatible` |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` / `OLLAMA_TIMEOUT` | `http://localhost:11434` / empty / `60` | local model runtime |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | empty | OpenAI-compatible fallback (OpenAI, LM Studio, …) |
| `STT_PROVIDER` / `STT_MODEL` | `local` / `base` | voice: `local` (faster-whisper or whisper.cpp) or `disabled` |
| `WHISPER_CPP_BIN` / `WHISPER_CPP_MODEL_PATH` | empty | whisper.cpp CLI + ggml model, if not using faster-whisper |
| `SEARCH_API_KEY` / `SEARCH_API_URL` | empty | real web search API (mock fallback otherwise) |
| `BROWSER_HEADLESS` | `false` | Playwright browser mode (`browser.open_url`) |
| `DEFAULT_BROWSER` | empty | e.g. `Safari`; empty = system default browser |
| `ALLOWED_APPLICATIONS` | common mac apps | comma-separated app allowlist for `desktop.open_application` |
| `ALLOWED_DIRECTORIES` | `~/Projects,~/Documents,~/Desktop,~/Downloads` | path allowlist for folder/terminal tools |
| `PROJECTS` | empty | JSON object: `{"griffin": "~/Projects/griffin"}` |
| `SEARCH_ENGINE_URL` | Google | `{query}` placeholder; used by `desktop.search_web` |
| `NEWS_SITES` / `RESEARCH_TOPIC` | HN / AI frameworks | morning + research workflow content |
| `DATABASE_URL` | `sqlite:///./griffin.db` | persistence |
| `GRIFFIN_DEV_TOKEN` | empty | reserved dev token |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | CORS |

**No keys needed to run.** Without an LLM configured, Griffin boots in deterministic mock-LLM mode: tools still really execute through the registry, and all demos below work.

## 3a. Ollama setup (local LLM)

```bash
brew install ollama          # if needed
ollama serve                 # or launch the Ollama app
ollama pull llama3.2         # any tool-capable model
```

Then set `LLM_PROVIDER=ollama` and `OLLAMA_MODEL=llama3.2` in `config/.env`.
Verify with `curl http://localhost:8000/api/health/ollama` — it reports
reachability, model presence, and a real inference probe. If the model is
missing, the endpoint tells you exactly what to `ollama pull`, and chat
requests fail with a human-readable `LLM_UNAVAILABLE` message.

## 3b. Voice / STT setup

Voice input uses a **local** speech-to-text engine (no cloud APIs):

- Preferred: `cd backend && . .venv/bin/activate && pip install faster-whisper` (model size from `STT_MODEL`, e.g. `base`).
- Or whisper.cpp: set `WHISPER_CPP_BIN` (e.g. `whisper-cli`) and `WHISPER_CPP_MODEL_PATH` (a `ggml-*.bin` model). Audio is converted to 16 kHz WAV with macOS `afconvert`.
- Or set `STT_PROVIDER=disabled` to hide voice entirely.

Check `curl http://localhost:8000/api/health/stt`. If no engine is available, the voice endpoint returns a structured `STT_UNAVAILABLE` error and the dashboard explains it.

## 4. Running the backend

```bash
cd backend && . .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload     # or: make backend
```

Check: `curl http://localhost:8000/api/health` → `{"status":"ok","service":"griffin","version":"0.1.0","llm_mode":"mock"}`

## 5. Running the frontend

```bash
cd frontend && npm run dev -- --host 0.0.0.0 --port 5173     # or: make frontend
```

Open http://localhost:5173.

## 6. Single-command development

```bash
./scripts/dev.sh            # or: make dev
```

Starts both servers (LAN-accessible), prints your LAN URL, and shuts both down cleanly on Ctrl-C.

## 7. LAN access from your phone

1. Run Griffin via `./scripts/dev.sh` (backend binds `0.0.0.0`, Vite runs with `--host`).
2. Find your Mac's LAN IP: `ipconfig getifaddr en0` (e.g. `192.168.1.42`).
3. On your phone (same Wi-Fi): open `http://192.168.1.42:5173`.

For microphone-only control on iPhone, create Griffin's local HTTPS identity once:

```bash
./scripts/setup-phone-https.sh
```

AirDrop `config/tls/griffin-ca.cer` to the iPhone, install **Griffin Local CA**
under **Settings → General → VPN & Device Management**, then enable full trust
under **Settings → General → About → Certificate Trust Settings**.
`dev.sh` automatically detects the generated certificate and prints an HTTPS
phone link. Certificates and private keys under `config/tls/` are gitignored.

The frontend derives the API/WebSocket host from the page's hostname, so chat, live events, and avatar state work from the phone with zero extra configuration. Dev servers are LAN-only — do not expose them to the public internet.

## 8. API endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | service status + `llm_mode` |
| GET | `/api/health/ollama` | Ollama reachability / model presence / inference probe |
| GET | `/api/health/stt` | speech-to-text provider + engine availability |
| GET | `/api/health/tools` | command registry inventory (name, permission, LLM visibility) |
| POST | `/api/chat` | `{"message": "...", "session_id": null}` → `{"message_id","task_id","session_id","response","tool_calls"}` |
| POST | `/api/voice` | raw audio body + `X-Session-Id` header → transcript + same shape as `/api/chat` |
| POST | `/api/remote/voice` | paired-phone audio with bearer token → local transcription + Griffin execution |
| GET | `/api/tasks/{task_id}` | task + its tool calls |
| GET | `/api/events?limit=50` | recent persisted events (chronological) |
| WS | `/ws` | live event stream (hello + last-20 replay on connect) |

## 9. WebSocket events

Envelope: `{"id","type","timestamp","session_id","task_id","data"}`.
Types: `SESSION_CREATED`, `MESSAGE_RECEIVED`, `TASK_STARTED`, `AGENT_STARTED`, `AGENT_THINKING`, `TOOL_CALL_STARTED`, `TOOL_CALL_COMPLETED`, `TOOL_CALL_FAILED`, `AGENT_RESPONSE`, `TASK_COMPLETED`, `TASK_FAILED`, `USER_APPROVAL_REQUIRED`, plus Phase 1: `STT_STARTED`, `STT_COMPLETED`, `STT_FAILED`, `WORKFLOW_STARTED`, `WORKFLOW_COMPLETED`.

Smoke-test the stream any time: `python scripts/ws_smoke.py`.

## 10. Available tools

| Tool | Permission | Behavior |
|---|---|---|
| `system.get_time` | safe | real local server time |
| `system.get_info` | safe | platform / python / host / app info |
| `web.search` | safe | real HTTP search if `SEARCH_API_*` set, otherwise explicit mock results |
| `browser.open_url` | safe | Playwright if installed (`playwright install chromium`), otherwise explicit mock executor |
| `desktop.open_application` | safe | open an allowlisted macOS app (`open -a`) |
| `desktop.open_url` | safe | open a validated http(s) URL in the default browser |
| `desktop.search_web` | safe | open a browser search (`SEARCH_ENGINE_URL` template) |
| `desktop.open_folder` | safe | open a folder inside `ALLOWED_DIRECTORIES` |
| `desktop.open_project` | safe | open a named project from `PROJECTS` (VS Code if available) |
| `desktop.open_terminal` | safe | open Terminal, optionally in an allowed directory |
| `workflow.run` | safe | run a registered workflow (see below) |
| `system.execute_shell` | **privileged** | registered stub, never exposed to the LLM, refuses execution |

Permissions: `safe` auto-executes · `confirm` emits `USER_APPROVAL_REQUIRED` (auto-approved in Phase 0/1 — the hook for a future approval UI) · `privileged` is hidden from the LLM and refuses execution.

### Registered workflows

| Workflow | Steps |
|---|---|
| `start_development` | VS Code → first configured project → GitHub |
| `research` | browser search for `RESEARCH_TOPIC` |
| `morning` | open each site in `NEWS_SITES` |

Workflows are pre-registered in `backend/tools/workflows.py`; the LLM can only select one by name — every step still passes through the same validation/execution boundary.

### Example phrases

"Open Safari" · "Open GitHub" · "Open VS Code" · "Open Terminal" ·
"Search the web for NXP S32K312 documentation" · "Open my griffin project" ·
"Open my Projects folder" · "Start my development environment"

## 11. Testing

```bash
make test            # backend pytest + frontend vitest
make test-backend    # config, LLM abstraction + Ollama provider (mocked HTTP),
                     # registry, tools, permissions, events/bus, DB, agent scenarios,
                     # Phase 1 desktop/workflow/validation boundary, voice endpoint, E2E
make test-frontend   # vitest: app render, avatar states/drag/persistence, ws parsing,
                     # state machine (incl. STT/workflow states), chat submit
```

All OS-level operations are mocked in tests — no real apps or browser windows open.

## 12. Troubleshooting

- **"Backend offline" badge** — backend not running or wrong port; the frontend targets `<page-hostname>:8000` unless `VITE_API_BASE` is set (`VITE_API_BASE=http://localhost:8000 npm run dev`).
- **Chat replies but no live events** — WebSocket blocked; check the connection dot, then `python scripts/ws_smoke.py`.
- **`browser.open_url` returns `"mock": true`** — install the browser once: `cd backend && . .venv/bin/activate && playwright install chromium`.
- **DB issues** — delete `backend/griffin.db`; tables recreate on startup.
- **CORS errors from LAN** — set `FRONTEND_ORIGIN` / use `VITE_API_BASE`; CORS already allows LAN origins in development.
- **Chat says the local model isn't reachable** — `curl http://localhost:8000/api/health/ollama`; start `ollama serve` and `ollama pull $OLLAMA_MODEL`.
- **Mic button errors with STT_UNAVAILABLE** — install a local engine (`pip install faster-whisper` in `backend/.venv`) or configure whisper.cpp; see §3b.
- **Phone microphone unavailable** — run `./scripts/setup-phone-https.sh`, install and trust `config/tls/griffin-ca.cer` on the iPhone, restart Griffin, and use the printed `https://` link. Griffin intentionally never falls back to video capture.
- **"Application not in the allowlist" / "outside the allowed directories"** — extend `ALLOWED_APPLICATIONS`, `ALLOWED_DIRECTORIES`, or `PROJECTS` in `config/.env`.
