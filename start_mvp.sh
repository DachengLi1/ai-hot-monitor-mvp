#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$ROOT/logs"
PID_DIR="$ROOT/run"
PORT="${PORT:-8890}"
mkdir -p "$LOG_DIR" "$PID_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "python3 not found. Please install Python 3 first."
  exit 1
fi

cd "$ROOT"

find_existing_pid() {
  local target="$1"
  pgrep -f "$ROOT/$target" | head -n 1 || true
}

ensure_pid_file_consistent() {
  local pid_file="$1"
  local target="$2"
  if [[ -f "$pid_file" ]]; then
    local pid
    pid="$(cat "$pid_file")"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      echo "$pid"
      return 0
    fi
    rm -f "$pid_file"
  fi

  local existing_pid
  existing_pid="$(find_existing_pid "$target")"
  if [[ -n "$existing_pid" ]]; then
    echo "$existing_pid" > "$pid_file"
    echo "$existing_pid"
    return 0
  fi

  echo ""
}

start_or_reuse() {
  local name="$1"
  local target="$2"
  local extra_env_name="${3:-}"
  local extra_env_value="${4:-}"
  local pid_file="$PID_DIR/$name.pid"
  local pid
  pid="$(ensure_pid_file_consistent "$pid_file" "$target")"

  if [[ -n "$pid" ]]; then
    echo "$name already running on PID $pid"
    return 0
  fi

  if [[ -n "$extra_env_name" ]]; then
    nohup env "$extra_env_name=$extra_env_value" "$PYTHON_BIN" "$ROOT/$target" > "$LOG_DIR/$name.log" 2>&1 &
  else
    nohup "$PYTHON_BIN" "$ROOT/$target" > "$LOG_DIR/$name.log" 2>&1 &
  fi
  pid=$!
  echo "$pid" > "$pid_file"
  echo "started $name PID $pid"
}

start_or_reuse "server" "server.py" "PORT" "$PORT"
start_or_reuse "fetch-loop" "run_fetch_loop.py"

echo "dashboard: http://127.0.0.1:$PORT"
