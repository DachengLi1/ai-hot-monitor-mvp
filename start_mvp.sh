#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="$(basename "$ROOT")"
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

process_cmdline() {
  local pid="$1"
  tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true
}

process_cwd() {
  local pid="$1"
  readlink -f "/proc/$pid/cwd" 2>/dev/null || true
}

find_existing_pid() {
  local target="$1"
  pgrep -f "$ROOT/$target" | head -n 1 || true
}

port_owner_pid() {
  local line
  line="$(ss -ltnp "( sport = :$PORT )" 2>/dev/null | grep -o 'pid=[0-9]\+' | head -n 1 || true)"
  if [[ -n "$line" ]]; then
    echo "${line#pid=}"
  fi
}

find_foreign_server() {
  local pid cmd cwd
  while read -r pid; do
    [[ -z "$pid" ]] && continue
    cmd="$(process_cmdline "$pid")"
    cwd="$(process_cwd "$pid")"
    [[ -z "$cmd" || -z "$cwd" ]] && continue
    [[ "$cmd" != *"server.py"* ]] && continue
    [[ "$(basename "$cwd")" != "$APP_NAME" ]] && continue
    if [[ "$cwd" != "$ROOT" ]]; then
      echo "$pid|$cwd|$cmd"
      return 0
    fi
  done < <(pgrep -f 'server.py' || true)
  return 1
}

find_foreign_loop() {
  local pid cmd cwd
  while read -r pid; do
    [[ -z "$pid" ]] && continue
    cmd="$(process_cmdline "$pid")"
    cwd="$(process_cwd "$pid")"
    [[ -z "$cmd" || -z "$cwd" ]] && continue
    [[ "$cmd" != *"run_fetch_loop.py"* ]] && continue
    [[ "$(basename "$cwd")" != "$APP_NAME" ]] && continue
    if [[ "$cwd" != "$ROOT" ]]; then
      echo "$pid|$cwd|$cmd"
      return 0
    fi
  done < <(pgrep -f 'run_fetch_loop.py' || true)
  return 1
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

ensure_server_port_safe() {
  local foreign pid cmd cwd
  foreign="$(find_foreign_server || true)"
  if [[ -n "$foreign" ]]; then
    IFS='|' read -r pid cwd cmd <<< "$foreign"
    echo "another $APP_NAME server is already running"
    echo "existing root: $cwd"
    echo "existing pid: $pid"
    echo "refusing to start a second server from: $ROOT"
    exit 1
  fi

  pid="$(port_owner_pid)"
  [[ -z "$pid" ]] && return 0

  cwd="$(process_cwd "$pid")"
  cmd="$(process_cmdline "$pid")"

  if [[ "$cwd" == "$ROOT" && "$cmd" == *"server.py"* ]]; then
    return 0
  fi

  if [[ "$(basename "$cwd")" == "$APP_NAME" && "$cmd" == *"server.py"* ]]; then
    echo "another $APP_NAME server already owns port $PORT"
    echo "existing root: $cwd"
    echo "refusing to start a second server from: $ROOT"
    exit 1
  fi

  echo "port $PORT is already occupied by another process: $cmd"
  exit 1
}

ensure_fetch_loop_safe() {
  local foreign
  foreign="$(find_foreign_loop || true)"
  [[ -z "$foreign" ]] && return 0

  IFS='|' read -r pid cwd cmd <<< "$foreign"
  echo "another $APP_NAME fetch loop is already running"
  echo "existing root: $cwd"
  echo "existing pid: $pid"
  echo "refusing to start a second fetch loop from: $ROOT"
  exit 1
}

start_or_reuse() {
  local name="$1"
  local target="$2"
  local extra_env_name="${3:-}"
  local extra_env_value="${4:-}"
  local pid_file="$PID_DIR/$name.pid"
  local pid

  if [[ "$name" == "server" ]]; then
    ensure_server_port_safe
  fi
  if [[ "$name" == "fetch-loop" ]]; then
    ensure_fetch_loop_safe
  fi

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

ensure_server_port_safe
ensure_fetch_loop_safe

start_or_reuse "server" "server.py" "PORT" "$PORT"

if systemctl --user is-active --quiet ai-hot-monitor-fetch.timer; then
  echo "fetch timer already managed by systemd user unit ai-hot-monitor-fetch.timer; skipping manual fetch-loop"
else
  start_or_reuse "fetch-loop" "run_fetch_loop.py"
fi

echo "root: $ROOT"
echo "dashboard: http://127.0.0.1:$PORT"
