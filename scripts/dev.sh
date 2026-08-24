#!/usr/bin/env bash
# Griffin Phase 0 — dev launcher: backend + frontend, LAN-accessible
set -euo pipefail
cd "$(dirname "$0")/.."

# shellcheck disable=SC1091
source .venv/bin/activate

HOST="${HOST:-0.0.0.0}"
REQUESTED_PORT="${PORT:-8000}"
PORT="$REQUESTED_PORT"

# The packaged Griffin app may already have its private kernel bound to
# 127.0.0.1:8000. macOS permits a second wildcard bind on the same port, but
# loopback requests then reach the packaged kernel instead of this development
# backend. Pick a free port and tell Vite exactly which backend it must proxy.
if command -v lsof >/dev/null 2>&1; then
  LAST_PORT=$((REQUESTED_PORT + 20))
  while lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t >/dev/null 2>&1; do
    PORT=$((PORT + 1))
    if [ "$PORT" -gt "$LAST_PORT" ]; then
      echo "Error: no free Griffin backend port found from ${REQUESTED_PORT} through ${LAST_PORT}." >&2
      exit 1
    fi
  done
fi
if [ "$PORT" != "$REQUESTED_PORT" ]; then
  echo "Port ${REQUESTED_PORT} is already used by another Griffin kernel; using ${PORT} for this session."
fi
export PORT
GRIFFIN_BACKEND_PROXY_TARGET="http://127.0.0.1:${PORT}"
export GRIFFIN_BACKEND_PROXY_TARGET

GRIFFIN_PROTOCOL="http"
DEFAULT_TLS_CERT="$(pwd)/config/tls/griffin.crt"
DEFAULT_TLS_KEY="$(pwd)/config/tls/griffin.key"
if [ -z "${GRIFFIN_TLS_CERT_FILE:-}" ] && [ -z "${GRIFFIN_TLS_KEY_FILE:-}" ] && \
   [ -f "$DEFAULT_TLS_CERT" ] && [ -f "$DEFAULT_TLS_KEY" ]; then
  GRIFFIN_TLS_CERT_FILE="$DEFAULT_TLS_CERT"
  GRIFFIN_TLS_KEY_FILE="$DEFAULT_TLS_KEY"
  export GRIFFIN_TLS_CERT_FILE GRIFFIN_TLS_KEY_FILE
fi
if { [ -n "${GRIFFIN_TLS_CERT_FILE:-}" ] && [ -z "${GRIFFIN_TLS_KEY_FILE:-}" ]; } || \
   { [ -z "${GRIFFIN_TLS_CERT_FILE:-}" ] && [ -n "${GRIFFIN_TLS_KEY_FILE:-}" ]; }; then
  echo "Error: set both GRIFFIN_TLS_CERT_FILE and GRIFFIN_TLS_KEY_FILE, or neither." >&2
  exit 1
fi

echo "Starting Griffin backend on ${HOST}:${PORT} ..."
if [ -n "${GRIFFIN_TLS_CERT_FILE:-}" ]; then
  GRIFFIN_PROTOCOL="https"
fi
uvicorn backend.main:app --host "$HOST" --port "$PORT" --reload &
BACKEND_PID=$!

echo "Starting Griffin frontend on 0.0.0.0:5173 ..."
(cd frontend && npm run dev -- --host 0.0.0.0 --port 5173) &
FRONTEND_PID=$!

cleanup() {
  echo "Shutting down Griffin..."
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo '<your-LAN-IP>')"
echo ""
echo "  Local:   ${GRIFFIN_PROTOCOL}://localhost:5173"
echo "  LAN:     ${GRIFFIN_PROTOCOL}://${LAN_IP}:5173   (open this from your phone on the same Wi-Fi)"
if [ "$GRIFFIN_PROTOCOL" = "http" ]; then
  echo "  Voice:   run ./scripts/setup-phone-https.sh once to enable the iPhone microphone"
fi
echo ""

wait
