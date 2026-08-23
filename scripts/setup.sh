#!/usr/bin/env bash
# Griffin Phase 0 — one-time setup
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Griffin setup =="

# Use a PyO3/pydantic-core compatible Python (3.11–3.13). The system default
# may be 3.14+, which cannot build pydantic-core wheels at this time.
PYTHON_BIN=""
for py in python3.12 python3.11 python3.13; do
  if command -v "$py" >/dev/null 2>&1; then
    PYTHON_BIN="$py"
    break
  fi
done
if [ -z "$PYTHON_BIN" ]; then
  echo "Error: no supported Python interpreter found (need python3.11, python3.12, or python3.13)." >&2
  exit 1
fi
echo "Using Python interpreter: $PYTHON_BIN"

# Backend
if [ ! -d .venv ]; then
  "$PYTHON_BIN" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r backend/requirements.txt

if [ ! -f config/.env ]; then
  cp config/.env.example config/.env
  echo "Created config/.env from .env.example (fill in LLM keys for live mode; mock mode works without)."
fi

# Optional: real browser tool (safe to skip — mock fallback kicks in)
if python -c "import playwright" 2>/dev/null; then
  echo "Playwright package present. Run 'playwright install chromium' once for the real browser.open_url tool."
else
  echo "Playwright not installed — browser.open_url will use its mock executor (interface intact)."
fi

# Frontend
(cd frontend && npm install)

echo ""
echo "Setup complete. Run:  ./scripts/dev.sh"
