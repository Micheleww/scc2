#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$REPO")"
LOG_DIR="${EXEC_LOG_DIR:-$REPO_ROOT/artifacts/executor_logs}"
mkdir -p "$LOG_DIR"

GATEWAY_PID="$LOG_DIR/gateway.pid"
WORKERS_PID="$LOG_DIR/ensure-workers.pid"
GATEWAY_OUT="$LOG_DIR/gateway.out.log"
GATEWAY_ERR="$LOG_DIR/gateway.err.log"
WORKERS_OUT="$LOG_DIR/ensure-workers.out.log"
WORKERS_ERR="$LOG_DIR/ensure-workers.err.log"

import_env_file() {
  local path="$1"
  local override="${2:-false}"
  [[ -f "$path" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    s="${line#"${line%%[![:space:]]*}"}"
    s="${s%"${s##*[![:space:]]}"}"
    [[ -n "$s" ]] || continue
    [[ "$s" == \#* ]] && continue
    [[ "$s" == *=* ]] || continue
    k="${s%%=*}"
    v="${s#*=}"
    k="${k#"${k%%[![:space:]]*}"}"
    k="${k%"${k##*[![:space:]]}"}"
    v="${v#"${v%%[![:space:]]*}"}"
    v="${v%"${v##*[![:space:]]}"}"
    [[ -n "$k" ]] || continue
    if [[ "$override" == "false" ]] && [[ -n "${!k:-}" ]]; then
      continue
    fi
    export "$k=$v"
  done < "$path"
}

read_pid() {
  local path="$1"
  [[ -f "$path" ]] || return 0
  local raw
  raw="$(cat "$path" 2>/dev/null)"
  raw="${raw#"${raw%%[![:space:]]*}"}"
  raw="${raw%"${raw##*[![:space:]]}"}"
  [[ -n "$raw" ]] || return 0
  local pid="$raw"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 0
  [[ "$pid" -gt 0 ]] || return 0
  kill -0 "$pid" 2>/dev/null || return 0
  echo "$pid"
}

write_pid() {
  local path="$1"
  local process_id="$2"
  echo "$process_id" > "$path"
}

get_listening_pid_by_port() {
  local port="$1"
  local pid
  pid="$(ss -tlnp 2>/dev/null | grep ":$port " | head -1 | grep -oP 'pid=\K[0-9]+' || true)"
  [[ -n "$pid" ]] || pid="$(netstat -tlnp 2>/dev/null | grep ":$port " | head -1 | awk '{print $NF}' | cut -d'/' -f1 || true)"
  [[ -n "$pid" ]] || return 0
  [[ "$pid" =~ ^[0-9]+$ ]] || return 0
  [[ "$pid" -gt 0 ]] || return 0
  kill -0 "$pid" 2>/dev/null || return 0
  echo "$pid"
}

start_gateway() {
  local existing
  existing="$(read_pid "$GATEWAY_PID")"
  if [[ -n "$existing" ]]; then
    echo "gateway already running pid=$existing"
    return 0
  fi
  [[ ! -f "$GATEWAY_PID" ]] || rm -f "$GATEWAY_PID"

  local env_file="$REPO/config/runtime.env"
  local env_example="$REPO/config/runtime.env.example"
  import_env_file "$env_example" false
  import_env_file "$env_file" true

  local need_install=false
  if [[ ! -d "$REPO/node_modules" ]]; then
    need_install=true
  elif [[ ! -d "$REPO/node_modules/http-proxy" ]]; then
    need_install=true
  fi
  if [[ "$need_install" == true ]] && [[ -f "$REPO/package-lock.json" ]]; then
    echo "installing gateway deps (npm ci)..."
    (cd "$REPO" && npm ci >/dev/null 2>&1) || true
  fi

  local port="${GATEWAY_PORT:-18788}"
  [[ "$port" =~ ^[0-9]+$ ]] || port=18788
  [[ "$port" -gt 0 ]] || port=18788

  local listening
  listening="$(get_listening_pid_by_port "$port")"
  if [[ -n "$listening" ]]; then
    echo "gateway already listening on $port pid=$listening"
    write_pid "$GATEWAY_PID" "$listening"
    return 0
  fi

  export GATEWAY_PORT="${GATEWAY_PORT:-18788}"
  export EXEC_CONCURRENCY_CODEX="${EXEC_CONCURRENCY_CODEX:-1}"
  export EXEC_CONCURRENCY_OPENCODE="${EXEC_CONCURRENCY_OPENCODE:-10}"
  export EXEC_TIMEOUT_CODEX_MS="${EXEC_TIMEOUT_CODEX_MS:-1200000}"
  export EXEC_TIMEOUT_OPENCODE_MS="${EXEC_TIMEOUT_OPENCODE_MS:-1200000}"
  export OPENCODE_MODEL="${OPENCODE_MODEL:-opencode/kimi-k2.5-free}"
  export MODEL_POOL_FREE="${MODEL_POOL_FREE:-opencode/kimi-k2.5-free}"
  export MODEL_POOL_VISION="${MODEL_POOL_VISION:-opencode/kimi-k2.5-free}"
  export DESIRED_RATIO_CODEX="${DESIRED_RATIO_CODEX:-0}"
  export DESIRED_RATIO_OPENCODECLI="${DESIRED_RATIO_OPENCODECLI:-10}"
  export EXTERNAL_MAX_CODEX="${EXTERNAL_MAX_CODEX:-0}"
  export EXTERNAL_MAX_OPENCODECLI="${EXTERNAL_MAX_OPENCODECLI:-10}"
  export WIP_BATCH_MAX="${WIP_BATCH_MAX:-4}"
  export WIP_BATCH_INTERNAL_MAX="${WIP_BATCH_INTERNAL_MAX:-${WIP_BATCH_MAX:-4}}"
  export WIP_BATCH_EXTERNAL_MAX="${WIP_BATCH_EXTERNAL_MAX:-2}"

  (cd "$REPO" && nohup node src/gateway.mjs > "$GATEWAY_OUT" 2> "$GATEWAY_ERR" &)
  local pid=$!
  write_pid "$GATEWAY_PID" "$pid"
  echo "gateway started pid=$pid port=$GATEWAY_PORT"
}

start_ensure_workers() {
  local existing
  existing="$(read_pid "$WORKERS_PID")"
  if [[ -n "$existing" ]]; then
    echo "ensure-workers already running pid=$existing"
    return 0
  fi
  [[ ! -f "$WORKERS_PID" ]] || rm -f "$WORKERS_PID"

  local env_file="$REPO/config/runtime.env"
  local env_example="$REPO/config/runtime.env.example"
  import_env_file "$env_example" false
  import_env_file "$env_file" true

  if [[ -z "${GATEWAY_BASE:-}" ]]; then
    local p="${GATEWAY_PORT:-18788}"
    [[ "$p" =~ ^[0-9]+$ ]] || p=18788
    [[ "$p" -gt 0 ]] || p=18788
    export GATEWAY_BASE="http://127.0.0.1:$p"
  fi

  local lock_file="$LOG_DIR/ensure_workers.lock.json"
  if [[ -f "$lock_file" ]]; then
    local lock_pid
    lock_pid="$(cat "$lock_file" 2>/dev/null | grep -o '"pid"[[:space:]]*:[[:space:]]*[0-9]*' | grep -o '[0-9]*' | head -1 || true)"
    if [[ -n "$lock_pid" ]] && [[ "$lock_pid" =~ ^[0-9]+$ ]] && [[ "$lock_pid" -gt 0 ]]; then
      if kill -0 "$lock_pid" 2>/dev/null; then
        echo "ensure-workers already running (lock pid=$lock_pid)"
        write_pid "$WORKERS_PID" "$lock_pid"
        return 0
      fi
    fi
  fi

  local script="$REPO/scripts/ensure-workers.sh"
  (cd "$REPO" && nohup bash "$script" > "$WORKERS_OUT" 2> "$WORKERS_ERR" &)
  local pid=$!
  write_pid "$WORKERS_PID" "$pid"
  echo "ensure-workers started pid=$pid"
}

start_gateway
start_ensure_workers

echo "OK. Health:"
p2="${GATEWAY_PORT:-18788}"
[[ "$p2" =~ ^[0-9]+$ ]] || p2=18788
[[ "$p2" -gt 0 ]] || p2=18788
echo "  http://127.0.0.1:$p2/pools"
echo "  http://127.0.0.1:$p2/board"
