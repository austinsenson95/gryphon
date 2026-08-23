#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
OUTPUT_ROOT="$PROJECT_ROOT/build/sidecar"
BINARY_DIR="$PROJECT_ROOT/frontend/src-tauri/binaries"

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Griffin desktop build requires $VENV_PYTHON. Run ./scripts/setup.sh first." >&2
  exit 1
fi

if ! "$VENV_PYTHON" -c "import PyInstaller" 2>/dev/null; then
  echo "PyInstaller is missing. Install desktop build dependencies with:" >&2
  echo "  $VENV_PYTHON -m pip install -r backend/requirements-desktop.txt" >&2
  exit 1
fi

TARGET_TRIPLE="$(rustc -Vv | awk '/^host:/ { print $2 }')"
if [[ -z "$TARGET_TRIPLE" ]]; then
  echo "Could not determine the Rust host target. Is rustc installed?" >&2
  exit 1
fi

rm -rf "$OUTPUT_ROOT"
mkdir -p "$OUTPUT_ROOT" "$BINARY_DIR"

cd "$PROJECT_ROOT"
"$VENV_PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --onefile \
  --name griffin-kernel \
  --distpath "$OUTPUT_ROOT/dist" \
  --workpath "$OUTPUT_ROOT/work" \
  --specpath "$OUTPUT_ROOT" \
  --collect-submodules backend \
  --collect-data faster_whisper \
  --hidden-import aiosqlite \
  backend/desktop_entry.py

install -m 755 \
  "$OUTPUT_ROOT/dist/griffin-kernel" \
  "$BINARY_DIR/griffin-kernel-$TARGET_TRIPLE"

echo "Built Griffin sidecar: $BINARY_DIR/griffin-kernel-$TARGET_TRIPLE"
