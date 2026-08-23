#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"$PROJECT_ROOT/scripts/build-sidecar.sh"
npm --prefix "$PROJECT_ROOT/frontend" run build
