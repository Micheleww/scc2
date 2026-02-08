#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$REPO")"
LOG_DIR="${EXEC_LOG_DIR:-$REPO_ROOT/artifacts/executor_logs}"
GATEWAY_PID="$LOG_DIR/gateway.pid"
WORKERS_PID="$LOG_DIR/ensure-workers.pid"

stop_by_pidfile() {
  local pid_file="$1"
  local label="$2"
  [[ -f "$pid_file" ]] || return 0
  local raw
  raw="$(cat "$pid_file" 2>/dev/null || true)"
  raw="${raw#"${raw%%[![:space:]]*}"}"
  raw="${raw%"${raw##*[![:space:]]}"}"
  [[ -n "$raw" ]] || return 0
  local pid="$raw"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 0
  [[ "$pid" -gt 0 ]] || return 0
  if kill -0 "$pid" 2>/dev/null; then
    echo "Stopping $label pid=$pid"
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$pid_file"
}

stop_by_script_needle() {
  local needle="$1"
  local label="$2"
  [[ -n "$needle" ]] || return 0
  local n="${needle//\\//}"
  n="${n,,}"
  local pids
  pids="$(ps aux 2>/dev/null | grep -i "$n" | grep -v grep | awk '{print $2}' || true)"
  for pid in $pids; do
    [[ "$pid" =~ ^[0-9]+$ ]] || continue
    [[ "$pid" -gt 0 ]] || continue
    echo "Stopping $label pid=$pid"
    kill -9 "$pid" 2>/dev/null || true
  done
}

stop_by_port() {
  local port="$1"
  local label="$2"
  local pid
  pid="$(ss -tlnp 2>/dev/null | grep ":$port " | head -1 | grep -oP 'pid=\K[0-9]+' || true)"
  [[ -n "$pid" ]] || pid="$(netstat -tlnp 2>/dev/null | grep ":$port " | head -1 | awk '{print $NF}' | cut -d'/' -f1 || true)"
  [[ -n "$pid" ]] || return 0
  [[ "$pid" =~ ^[0-9]+$ ]] || return 0
  [[ "$pid" -gt 0 ]] || return 0
  if kill -0 "$pid" 2>/dev/null; then
    echo "Stopping $label (port $port) pid=$pid"
    kill -9 "$pid" 2>/dev/null || true
  fi
}

stop_by_pidfile "$WORKERS_PID" "ensure-workers"
stop_by_pidfile "$GATEWAY_PID" "gateway"

stop_by_script_needle "scripts/worker-codex.sh" "codex worker"
stop_by_script_needle "scripts/worker-opencodecli.sh" "opencodecli worker"

stop_by_port 18788 "gateway"

echo "Stopped."
