#!/usr/bin/env bash
# Start local Airflow standalone (tmux when available, nohup fallback for Cloud Shell).
set -euo pipefail

ATLAS_ROOT="${ATLAS_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
# shellcheck disable=SC1091
source "${ATLAS_ROOT}/scripts/airflow_env.sh"

SESSION="atlas-airflow-local"
PIDFILE="${AIRFLOW_HOME}/standalone.pid"
LOGFILE="${AIRFLOW_HOME}/standalone.log"
mkdir -p "$AIRFLOW_HOME"

if [[ -f "$PIDFILE" ]]; then
  pid="$(cat "$PIDFILE")"
  if kill -0 "$pid" 2>/dev/null; then
    echo "Airflow standalone already running (pid=$pid)"
    exit 0
  fi
  rm -f "$PIDFILE"
fi

start_standalone() {
  nohup airflow standalone >>"$LOGFILE" 2>&1 &
  echo $! >"$PIDFILE"
  echo "Started Airflow standalone (pid=$(cat "$PIDFILE"), log=$LOGFILE)"
}

if command -v tmux >/dev/null 2>&1; then
  TMUX_CMD=(tmux)
  if [[ -f /exec-daemon/tmux.portal.conf ]]; then
    TMUX_CMD=(tmux -f /exec-daemon/tmux.portal.conf)
  fi
  if "${TMUX_CMD[@]}" has-session -t "=$SESSION" 2>/dev/null; then
    echo "Airflow session already running: $SESSION"
    exit 0
  fi
  if "${TMUX_CMD[@]}" new-session -d -s "$SESSION" -c "$ATLAS_ROOT" -- \
    bash -lc "source '${ATLAS_ROOT}/scripts/airflow_env.sh' && airflow standalone"; then
    echo "Started Airflow standalone in tmux session: $SESSION"
    exit 0
  fi
  echo "tmux unavailable or failed; falling back to nohup" >&2
fi

start_standalone
