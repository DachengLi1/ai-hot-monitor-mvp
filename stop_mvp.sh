#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_DIR="$ROOT/run"

for name in server fetch-loop; do
  pid_file="$PID_DIR/$name.pid"
  if [[ -f "$pid_file" ]]; then
    pid="$(cat "$pid_file")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid"
      echo "stopped $name PID $pid"
    else
      echo "$name not running"
    fi
    rm -f "$pid_file"
  else
    echo "$name pid file not found"
  fi
done
