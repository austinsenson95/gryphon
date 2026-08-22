# Gryphon — Phase 0

A **local-first personal AI assistant**. Your Mac (or any machine) is the server; the web dashboard is Gryphon's world — a draggable avatar, live activity feed, chat, task state, and tool activity, all streaming over WebSocket.

![Gryphon dashboard](docs/dashboard.png)

Phase 0 is the minimum viable skeleton, built as a **modular monolith**: one FastAPI backend, one React frontend, SQLite persistence. Everything is designed so future capabilities (browser automation, messaging, memory, voice, multi-agent) plug in without rewriting the core.

## 1. Architecture

```text
USER → WEB APP → GRYPHON API → AGENT/LLM → TOOL REGISTRY → TOOL EXECUTION
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
| `APP_NAME` / `ENVIRONMENT` | `Gryphon` / `development` | service identity |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | bind address (LAN-accessible) |
| `LLM_PROVIDER` | `openai_compatible` | provider key |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | empty | live LLM credentials (OpenAI, or any OpenAI-compatible endpoint e.g. Ollama/LM Studio) |
| `SEARCH_API_KEY` / `SEARCH_API_URL` | empty | real web search (mock fallback otherwise) |
| `BROWSER_HEADLESS` | `false` | Playwright browser mode |
| `DATABASE_URL` | `sqlite:///./gryphon.db` | persistence |
| `GRYPHON_DEV_TOKEN` | empty | reserved dev token |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | CORS |

**No keys needed to run.** Without `LLM_API_KEY`, Gryphon boots in deterministic mock-LLM mode: tools still really execute through the registry, and all demos below work.

## 4. Running the backend

```bash
cd backend && . .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload     # or: make backend
```

Check: `curl http://localhost:8000/api/health` → `{"status":"ok","service":"gryphon","version":"0.1.0","llm_mode":"mock"}`

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

1. Run Gryphon via `./scripts/dev.sh` (backend binds `0.0.0.0`, Vite runs with `--host`).
2. Find your Mac's LAN IP: `ipconfig getifaddr en0` (e.g. `192.168.1.42`).
3. On your phone (same Wi-Fi): open `http://192.168.1.42:5173`.

The frontend derives the API/WebSocket host from the page's hostname, so chat, live events, and avatar state work from the phone with zero extra configuration. Dev servers are LAN-only — do not expose them to the public internet.

## 8. API endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | service status + `llm_mode` |
| POST | `/api/chat` | `{"message": "...", "session_id": null}` → `{"message_id","task_id","session_id","response","tool_calls"}` |
| GET | `/api/tasks/{task_id}` | task + its tool calls |
| GET | `/api/events?limit=50` | recent persisted events (chronological) |
| WS | `/ws` | live event stream (hello + last-20 replay on connect) |

## 9. WebSocket events

Envelope: `{"id","type","timestamp","session_id","task_id","data"}`.
Types: `SESSION_CREATED`, `MESSAGE_RECEIVED`, `TASK_STARTED`, `AGENT_STARTED`, `AGENT_THINKING`, `TOOL_CALL_STARTED`, `TOOL_CALL_COMPLETED`, `TOOL_CALL_FAILED`, `AGENT_RESPONSE`, `TASK_COMPLETED`, `TASK_FAILED`, `USER_APPROVAL_REQUIRED`.

Smoke-test the stream any time: `python scripts/ws_smoke.py`.

## 10. Available tools

| Tool | Permission | Behavior |
|---|---|---|
| `system.get_time` | safe | real local server time |
| `system.get_info` | safe | platform / python / host / app info |
| `web.search` | safe | real HTTP search if `SEARCH_API_*` set, otherwise explicit mock results |
| `browser.open_url` | safe | Playwright if installed (`playwright install chromium`), otherwise explicit mock executor |
| `system.execute_shell` | **privileged** | registered stub, never exposed to the LLM, refuses execution |

Permissions: `safe` auto-executes · `confirm` emits `USER_APPROVAL_REQUIRED` (auto-approved in Phase 0 — the hook for a future approval UI) · `privileged` is hidden from the LLM.

## 11. Testing

```bash
make test            # backend pytest (46) + frontend vitest (26)
make test-backend    # pytest: config, LLM abstraction, registry, tools, permissions,
                     # events/bus, DB, agent scenarios, E2E chat→tool→events lifecycle
make test-frontend   # vitest: app render, avatar states/drag/persistence, ws parsing,
                     # state machine, chat submit
```

## 12. Troubleshooting

- **"Backend offline" badge** — backend not running or wrong port; the frontend targets `<page-hostname>:8000` unless `VITE_API_BASE` is set (`VITE_API_BASE=http://localhost:8000 npm run dev`).
- **Chat replies but no live events** — WebSocket blocked; check the connection dot, then `python scripts/ws_smoke.py`.
- **`browser.open_url` returns `"mock": true`** — install the browser once: `cd backend && . .venv/bin/activate && playwright install chromium`.
- **DB issues** — delete `backend/gryphon.db`; tables recreate on startup.
- **CORS errors from LAN** — set `FRONTEND_ORIGIN` / use `VITE_API_BASE`; CORS already allows LAN origins in development.
