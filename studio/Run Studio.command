#!/bin/zsh
set -euo pipefail

# Runs from wherever this project lives; no hard-coded paths.
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PORT="8789"
LOG_FILE="$PROJECT_DIR/runtime/studio/studio-server.log"

cd "$PROJECT_DIR"
mkdir -p "$PROJECT_DIR/runtime/studio"

if ! /usr/sbin/lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  /usr/bin/nohup /usr/bin/env node studio/server.mjs > "$LOG_FILE" 2>&1 &
  sleep 1
fi

STUDIO_URL="http://localhost:${PORT}/studio/"
/usr/bin/open "$STUDIO_URL"
