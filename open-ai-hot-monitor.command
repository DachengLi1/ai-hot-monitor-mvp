#!/bin/bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${PORT:-8890}"

bash "$DIR/start_mvp.sh" || true
sleep 1
open "http://127.0.0.1:$PORT/"
