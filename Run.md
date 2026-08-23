# Griffin — Setup & Run Guide

This document explains how to get the Griffin backend and frontend running on your machine.

## Requirements

- **Python** 3.11, 3.12, or 3.13 (3.14 is **not** supported because `pydantic-core` cannot build wheels for it yet).
- **Node.js** with `npm` (for the Vite + React frontend).
- macOS, Linux, or WSL (commands below use `bash`).

> If your default `python3` is 3.14, the setup script will automatically pick `python3.12`, `python3.11`, or `python3.13` if any of them is installed.

## Quick Start

From the project root (`griffin/`):

```bash
# 1. One-time setup (creates .venv, installs Python + Node deps, copies env file)
./scripts/setup.sh

# 2. Start both backend and frontend dev servers
./scripts/dev.sh
```

Then open the dashboard at **http://localhost:5173**.

The first command also creates `config/.env` from `config/.env.example`. Mock mode works without any API keys; fill in `LLM_API_KEY` only if you want to use a live LLM.

---

## Manual Setup

If you prefer to run each step yourself:

### 1. Create the Python virtual environment

```bash
# Use a supported interpreter (example: python3.12)
python3.12 -m venv .venv
source .venv/bin/activate
```

### 2. Install backend dependencies

```bash
pip install --upgrade pip
pip install -r backend/requirements.txt
```

### 3. Create the environment file

```bash
cp config/.env.example config/.env
```

Edit `config/.env` if you want to configure a live LLM, search API, or STT provider. The defaults run Griffin in mock mode, which works without credentials.

### 4. Install frontend dependencies

```bash
cd frontend && npm install
```

---

## Running the Application

### Both servers (recommended for development)

```bash
./scripts/dev.sh
```

This starts:

- **Backend**: `uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload`
- **Frontend**: `npm run dev -- --host 0.0.0.0 --port 5173`

Press `Ctrl-C` to stop both.

### Backend only

```bash
source .venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Health check:

```bash
curl http://localhost:8000/api/health
```

### Frontend only

```bash
cd frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

---

## Troubleshooting

### `pydantic-core` fails to build / PyO3 version error

Your virtual environment is probably using Python 3.14. Recreate it with a supported interpreter:

```bash
rm -rf .venv
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### Port already in use

Set a different port before running:

```bash
PORT=8001 ./scripts/dev.sh
```

### Frontend cannot reach the backend

Make sure the backend is running and that `FRONTEND_ORIGIN` in `config/.env` matches the frontend URL (default: `http://localhost:5173`).

---

## Running Tests

### Backend tests

```bash
source .venv/bin/activate
pytest tests/backend
```

### Frontend tests

```bash
cd frontend
npm test
```

---

## Optional: Real Browser Tool

The `browser.open_url` tool uses a mock fallback by default. To enable real browser execution, install Playwright:

```bash
source .venv/bin/activate
pip install playwright
playwright install chromium
```
