#!/usr/bin/env bash
# Gryphon Phase 0 — one-time setup
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Gryphon setup =="

# Backend
if [ ! -d .venv ]; then
  python3 -m venv .venv
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
