#!/usr/bin/env bash
set -euo pipefail

ATLAS_ROOT="${ATLAS_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
PIDFILE="${ATLAS_ROOT}/.airflow/standalone.pid"
SESSION="atlas-airflow-local"

if command -v tmux >/dev/null 2>&1; then
  TMUX_CMD=(tmux)
  if [[ -f /exec-daemon/tmux.portal.conf ]]; then
    TMUX_CMD=(tmux -f /exec-daemon/tmux.portal.conf)
  fi
  "${TMUX_CMD[@]}" kill-session -t "$SESSION" 2>/dev/null || true
fi

if [[ -f "$PIDFILE" ]]; then
  pid="$(cat "$PIDFILE")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    echo "Stopped Airflow standalone (pid=$pid)"
  fi
  rm -f "$PIDFILE"
else
  echo "No Airflow standalone pid file found"
fi
