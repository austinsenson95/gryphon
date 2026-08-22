#!/usr/bin/env bash
# Gryphon Phase 0 — dev launcher: backend + frontend, LAN-accessible
set -euo pipefail
cd "$(dirname "$0")/.."

# shellcheck disable=SC1091
source .venv/bin/activate

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

echo "Starting Gryphon backend on ${HOST}:${PORT} ..."
uvicorn backend.main:app --host "$HOST" --port "$PORT" --reload &
BACKEND_PID=$!

echo "Starting Gryphon frontend on 0.0.0.0:5173 ..."
(cd frontend && npm run dev -- --host 0.0.0.0 --port 5173) &
FRONTEND_PID=$!

cleanup() {
  echo "Shutting down Gryphon..."
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo '<your-LAN-IP>')"
echo ""
echo "  Local:   http://localhost:5173"
echo "  LAN:     http://${LAN_IP}:5173   (open this from your phone on the same Wi-Fi)"
echo ""

wait
