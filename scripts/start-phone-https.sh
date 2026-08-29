#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/config/.env"
RUNTIME_TARGET_FILE="$PROJECT_ROOT/.griffin-dev-backend"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi

NGROK_AUTHTOKEN=""
while IFS='=' read -r key value; do
  if [[ "$key" == "NGROK_AUTHTOKEN" ]]; then
    NGROK_AUTHTOKEN="$value"
    break
  fi
done < "$ENV_FILE"
export NGROK_AUTHTOKEN

if [[ -z "${NGROK_AUTHTOKEN:-}" ]]; then
  echo "NGROK_AUTHTOKEN is not configured in config/.env" >&2
  exit 1
fi

if [[ -z "${PHONE_GATEWAY_TARGET:-}" && -f "$RUNTIME_TARGET_FILE" ]]; then
  PHONE_GATEWAY_TARGET="$(sed -n '1p' "$RUNTIME_TARGET_FILE")"
fi
export PHONE_GATEWAY_TARGET="${PHONE_GATEWAY_TARGET:-http://127.0.0.1:8000}"

if ! [[ "$PHONE_GATEWAY_TARGET" =~ ^http://127\.0\.0\.1:[0-9]+$ ]]; then
  echo "Invalid PHONE_GATEWAY_TARGET: $PHONE_GATEWAY_TARGET" >&2
  exit 1
fi

if ! curl --silent --show-error --fail --max-time 3 "$PHONE_GATEWAY_TARGET/api/health" >/dev/null; then
  echo "Griffin development backend is not reachable at $PHONE_GATEWAY_TARGET." >&2
  echo "Start ./scripts/dev.sh first, then rerun this launcher." >&2
  exit 1
fi

echo "Forwarding authenticated phone callbacks to $PHONE_GATEWAY_TARGET"

GATEWAY_PORT="${PHONE_GATEWAY_PORT:-8003}"
UVICORN="$PROJECT_ROOT/backend/.venv/bin/uvicorn"
if [[ ! -x "$UVICORN" ]]; then
  echo "Missing Griffin backend environment. Run ./scripts/setup.sh first." >&2
  exit 1
fi

"$UVICORN" scripts.phone_webhook_gateway:app --host 127.0.0.1 --port "$GATEWAY_PORT" &
GATEWAY_PID=$!
cleanup() {
  kill "$GATEWAY_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Use an explicit IPv4 upstream. On recent macOS/ngrok builds, "localhost"
# can resolve to ::1 while the narrow gateway intentionally listens only on
# 127.0.0.1, causing Vobiz answer callbacks to fail with ERR_NGROK_8012.
ngrok http "http://127.0.0.1:$GATEWAY_PORT" --log stdout
