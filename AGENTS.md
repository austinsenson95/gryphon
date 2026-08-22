# Gryphon — Agent Guide

Gryphon is a **local-first personal AI assistant** (Phase 0). The backend runs on your machine and serves a React dashboard with a draggable avatar, live activity feed, chat, task state, and tool activity. All state changes stream to the browser over a single WebSocket.

This document reflects the actual file tree and code as it exists today.

## Project Overview

```text
USER → WEB APP → GRYPHON API → AGENT/LLM → TOOL REGISTRY → TOOL EXECUTION
                                      ↓
                                 EVENT BUS  ──→ SQLite (persisted)
                                      ↓
                             WEBSOCKET → DASHBOARD + AVATAR
```

- **Backend** (`backend/`) — FastAPI (Python 3.11+). REST endpoints, WebSocket endpoint, agent runtime, LLM provider abstraction, tool registry, event bus, SQLite persistence via SQLAlchemy 2.x async.
- **Frontend** (`frontend/`) — Vite + React 18 + TypeScript + Tailwind CSS. Glassmorphism dashboard built around a `GlassCard` primitive; event-driven state (no polling); draggable avatar with a 7-state state machine.
- **Persistence** — SQLite (`sqlite+aiosqlite`). Tables auto-create on startup.
- **Configuration** — `config/.env` (see `config/.env.example`). Never commit `.env`.

The agent runtime never hard-codes an LLM provider or tool set; both come from abstractions (`backend/llm/base.py`, `backend/tools/registry.py`).

## Technology Stack

### Backend

| Layer | Choice |
|-------|--------|
| Framework | FastAPI 0.115.6 |
| Server | uvicorn[standard] 0.32.1 |
| Validation / settings | pydantic 2.10.3, pydantic-settings 2.6.1 |
| DB ORM | SQLAlchemy 2.0.36 async + aiosqlite 0.20.0 |
| HTTP client | httpx 0.27.2 |
| LLM SDK | openai 1.55.3 (OpenAI-compatible endpoints, including local ones) |
| WebSocket | websockets 13.1 + FastAPI native `WebSocket` |
| Testing | pytest 8.3.4, pytest-asyncio 0.24.0, asgi-lifespan 2.1.0 |
| Optional real browser | Playwright (not in `requirements.txt`; must be installed separately) |

### Frontend

| Layer | Choice |
|-------|--------|
| Build tool | Vite 5.4.11 |
| Framework | React 18.3.1, react-dom 18.3.1 |
| Language | TypeScript ~5.6.3 |
| Styling | Tailwind CSS 3.4.17, autoprefixer, postcss |
| Components | Radix UI primitives (`@radix-ui/react-label`, `@radix-ui/react-slot`), lucide-react icons |
| Utilities | class-variance-authority, clsx, tailwind-merge |
| Testing | vitest 2.1.8, jsdom, @testing-library/react/jest-dom/user-event |
| Linting | oxlint configured in `frontend/.oxlintrc.json` (React + TypeScript + oxc rules) |

## Directory Layout

```text
gryphon/
├── backend/                 # FastAPI Python backend
│   ├── api/                 # REST + WebSocket routers
│   ├── core/                # Config, logging, agent runtime, planner, permissions, state
│   ├── events/              # Event bus, event envelope, WebSocket manager
│   ├── llm/                 # LLM provider abstraction + OpenAI-compatible + mock providers
│   ├── memory/              # SQLAlchemy models + data-access functions
│   ├── services/            # Message / task / notification services
│   ├── tools/               # Tool registry, schemas, built-in tool modules
│   │   ├── browser/         # browser.open_url (Playwright or mock fallback)
│   │   ├── research/        # web.search (real HTTP or mock fallback)
│   │   └── terminal/        # system.get_time, system.get_info, system.execute_shell
│   └── main.py              # Application factory; ASGI entry point: backend.main:app
├── frontend/                # Vite React frontend
│   ├── src/
│   │   ├── activity/        # Activity timeline UI
│   │   ├── avatar/          # Avatar renderer + 7-state state machine
│   │   ├── components/ui/   # GlassCard, Button, Input, Label, GhibliRobotHero
│   │   ├── dashboard/       # Chat panel
│   │   ├── lib/             # API client, WS client, types, utils, GryphonProvider
│   │   ├── notifications/   # Toast stack
│   │   └── tasks/           # Current task + tool activity cards
│   ├── tests live in ../../tests/frontend (configured in vite.config.ts)
│   └── index.html
├── tests/
│   ├── backend/             # pytest suite
│   └── frontend/            # vitest suite + setup.ts
├── scripts/
│   ├── setup.sh             # One-time dependency + .env setup
│   ├── dev.sh               # Run backend + frontend together (LAN-accessible)
│   └── ws_smoke.py          # WebSocket lifecycle smoke test
├── config/
│   ├── .env.example         # Env template
│   └── .env                 # Local secrets (created by setup.sh, gitignored)
├── avatar/idle/             # Static avatar image + background
└── README.md
```

## Configuration

Environment variables are read from `config/.env` (path hard-coded in `backend/core/config.py`).

| Variable | Default | Purpose |
|---|---|---|
| `APP_NAME` | `Gryphon` | service identity |
| `ENVIRONMENT` | `development` | runtime environment |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | backend bind address |
| `LLM_PROVIDER` | `openai_compatible` | provider selector |
| `LLM_API_KEY` | empty | live LLM credentials |
| `LLM_BASE_URL` | empty | OpenAI-compatible base URL (e.g. Ollama/LM Studio) |
| `LLM_MODEL` | empty | model name; fallback `gpt-4o-mini` in live mode |
| `SEARCH_API_KEY` / `SEARCH_API_URL` | empty | real web search (mock fallback otherwise) |
| `BROWSER_HEADLESS` | `false` | Playwright headless mode |
| `DATABASE_URL` | `sqlite:///./gryphon.db` | SQLite path |
| `GRYPHON_DEV_TOKEN` | empty | reserved dev token |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | CORS origin |

No API keys are required to run. Without `LLM_API_KEY` Gryphon boots in deterministic mock-LLM mode; tool calls from the mock provider are still executed through the real registry.

## Build and Run Commands

### First-time setup

```bash
./scripts/setup.sh
```

This creates `backend/.venv`, installs backend + frontend dependencies, and copies `config/.env.example` to `config/.env`.

### Development (both servers)

```bash
./scripts/dev.sh
```

- Backend: `uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload`
- Frontend: `npm run dev -- --host 0.0.0.0 --port 5173`
- Prints local and LAN URLs; Ctrl-C shuts both down.

### Run backend only

```bash
cd backend && source ../.venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Health check: `curl http://localhost:8000/api/health`

### Run frontend only

```bash
cd frontend && npm run dev -- --host 0.0.0.0 --port 5173
```

### Tests

There is no `Makefile` in the repo despite the README mentioning `make` targets. Run tests directly:

Backend:

```bash
cd backend && source ../.venv/bin/activate
pytest ../tests/backend
```

Frontend:

```bash
cd frontend && npm test
```

### Smoke test

With the backend running:

```bash
python scripts/ws_smoke.py [--host 127.0.0.1] [--port 8000]
```

## API and WebSocket Contracts

### REST Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | service status + `llm_mode` |
| POST | `/api/chat` | `{"message": "...", "session_id": null}` → chat response |
| GET | `/api/tasks/{task_id}` | task + its tool calls |
| GET | `/api/events?limit=50` | recent persisted events (chronological) |
| WS | `/ws` | live event stream (hello + last-20 replay on connect) |

### WebSocket Event Envelope

```json
{
  "id": "evt_<uuid>",
  "type": "TOOL_CALL_STARTED",
  "timestamp": "2026-01-01T00:00:00Z",
  "session_id": "...",
  "task_id": "...",
  "data": {}
}
```

Event types: `SESSION_CREATED`, `MESSAGE_RECEIVED`, `TASK_STARTED`, `AGENT_STARTED`, `AGENT_THINKING`, `TOOL_CALL_STARTED`, `TOOL_CALL_COMPLETED`, `TOOL_CALL_FAILED`, `AGENT_RESPONSE`, `TASK_COMPLETED`, `TASK_FAILED`, `USER_APPROVAL_REQUIRED`.

## Code Organization and Conventions

### Backend

- **App factory pattern**: `backend.main:create_app(settings=None)` builds the FastAPI app. The app instance is `backend.main:app`.
- **Lifespan wiring**: DB tables, tool registry, LLM provider, WebSocket manager, and event bus are created in the lifespan and stored in `app.state.gryphon` (`backend.core.state.AppState`).
- **Services + repository pattern**: `backend/services/*.py` hold high-level operations; `backend/memory/retrieval.py` holds raw data-access functions. **Important**: the current code imports `from backend.memory import retrieval` but many call sites reference an undefined name `repository`. See Known Issues below.
- **Logging**: `backend.core.logging` provides JSON-line structured logging. Never log secrets/API keys.
- **Tool model**: `backend/tools/schemas.py` defines `Tool` (name, description, JSON input schema, permission, async handler) and `ToolResult`. `ToolRegistry.openai_schemas()` hides `privileged` tools from the LLM.
- **Permissions**: `safe` auto-executes; `confirm` emits `USER_APPROVAL_REQUIRED` (auto-approved in Phase 0); `privileged` refuses execution.

### Frontend

- **Path alias**: `@/` maps to `frontend/src/`.
- **Presentational primitive**: `frontend/src/components/ui/glass-card.tsx` exports `GlassCard*` and is the base for most dashboard surfaces.
- **State management**: `GryphonProvider` (`frontend/src/lib/useGryphonEvents.tsx`) is a React context that seeds events from `/api/events`, subscribes to `/ws`, and derives UI state (current task, tool activity, notifications, avatar state).
- **Avatar isolation**: `AvatarRenderer` only receives `AvatarState`; it does not know about chat or tasks. Click dispatches `gryphon:avatar-activate`; double-click recenters; drag position persists to `localStorage`.
- **LAN-friendly URLs**: `frontend/src/lib/api.ts` derives `API_BASE` from `location.hostname` and port `8000`, unless `VITE_API_BASE` is set at build time.
- **Types**: `frontend/src/lib/types.ts` mirrors the backend event envelope and API contracts.

## Testing Strategy

- **Backend tests** (`tests/backend/`): isolated per-test app + temp SQLite via `conftest.py` fixtures. Covers config, DB round-trips, LLM abstraction, mock provider, tool registry/executor, permissions, event bus, agent scenarios, and end-to-end HTTP + WebSocket lifecycle.
- **Frontend tests** (`tests/frontend/`): Vitest + jsdom + Testing Library. Covers app render, avatar states/drag/persistence, WS parsing, state machine, and chat submit. `tests/frontend/setup.ts` stubs `WebSocket`, `fetch`, and `PointerEvent`.

## Security Considerations

- The only privileged tool, `system.execute_shell`, is registered but explicitly refuses execution in Phase 0.
- API keys and `GRYPHON_DEV_TOKEN` live only in `config/.env`, which is gitignored.
- CORS allows the configured `FRONTEND_ORIGIN` plus localhost/127.0.0.1 and common LAN IP ranges (`192.168.x.x`, `10.x.x.x`, `172.16-31.x.x`). Dev servers are intended for LAN-only use, not public exposure.
- Structured logging is configured to avoid emitting reserved log fields; secrets must never be passed into `extra={...}`.

## Known Issues (as of current checkout)

1. **`repository` vs `retrieval` naming mismatch** — Multiple backend files import `from backend.memory import retrieval` but call functions on an undefined `repository` name. Affected files include:
   - `backend/main.py`
   - `backend/core/agent.py`
   - `backend/events/bus.py`
   - `backend/api/events.py`
   - `backend/services/message_service.py`
   - `backend/services/task_service.py`
   - `backend/services/notification_service.py`
   - `tests/backend/test_db.py`
   - `tests/backend/test_events.py`

   These references should likely be `retrieval.<function>` (the functions defined in `backend/memory/retrieval.py`). Until fixed, the backend will raise `NameError` at runtime and tests will fail to collect/run.

2. **README inaccuracies** — `README.md` references paths/commands that do not match the repo:
   - It says configuration lives in `backend/.env` / `backend/.env.example`; the actual files are `config/.env` and `config/.env.example`.
   - It says to run `uvicorn app.main:app`; the actual entry point is `backend.main:app`.
   - It documents `make` commands (`make test`, `make backend`, etc.), but no `Makefile` exists.

3. **Playwright not pinned** — The real `browser.open_url` tool relies on Playwright, which is not listed in `backend/requirements.txt` and must be installed manually.

## Dependencies and Tooling Notes

- Python virtual environment is expected at `backend/.venv` (created by `setup.sh`).
- Frontend dependencies live in `frontend/node_modules`.
- The backend uses `from __future__ import annotations` consistently for forward references.
- TypeScript strict mode is enabled; unused locals/parameters are errors.
