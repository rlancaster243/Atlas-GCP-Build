#!/usr/bin/env bash
# Trigger an Atlas Sprint 3 DAG run and poll it to a terminal state.
#
# Exit codes:
#   0  the DAG run reached terminal state "success"
#   1  usage error, DAG not registered, trigger failure, run failure, or timeout
set -euo pipefail

ATLAS_ROOT="${ATLAS_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
# shellcheck disable=SC1091
source "${ATLAS_ROOT}/scripts/airflow_env.sh"

PROCESSING_DATE=""
BATCH_ID=""
CONF_JSON="{}"
RUN_ID=""
WAIT_SECONDS="${WAIT_SECONDS:-120}"
# Upper bound for the run itself (trigger to terminal state).
RUN_TIMEOUT_SECONDS="${RUN_TIMEOUT_SECONDS:-1800}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-10}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --processing-date) PROCESSING_DATE="$2"; shift 2 ;;
    --batch-id) BATCH_ID="$2"; shift 2 ;;
    --conf) CONF_JSON="$2"; shift 2 ;;
    --run-id) RUN_ID="$2"; shift 2 ;;
    --wait-seconds) WAIT_SECONDS="$2"; shift 2 ;;
    --run-timeout-seconds) RUN_TIMEOUT_SECONDS="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

# Merge overrides into the conf JSON. Values are passed via the environment
# (never interpolated into the Python source) so quotes or shell metacharacters
# in a value cannot corrupt the JSON or inject code.
if [[ -n "$PROCESSING_DATE" || -n "$BATCH_ID" ]]; then
  CONF_JSON="$(
    ATLAS_CONF="$CONF_JSON" ATLAS_PD="$PROCESSING_DATE" ATLAS_BID="$BATCH_ID" python3 - <<'PY'
import json
import os

conf = json.loads(os.environ.get("ATLAS_CONF") or "{}")
if os.environ.get("ATLAS_PD"):
    conf["processing_date"] = os.environ["ATLAS_PD"]
if os.environ.get("ATLAS_BID"):
    conf["batch_id"] = os.environ["ATLAS_BID"]
print(json.dumps(conf))
PY
  )"
fi

echo "Waiting up to ${WAIT_SECONDS}s for atlas_batch_pipeline to register..."
deadline=$((SECONDS + WAIT_SECONDS))
while (( SECONDS < deadline )); do
  if airflow dags list 2>/dev/null | awk '{print $1}' | grep -qx "atlas_batch_pipeline"; then
    break
  fi
  if airflow dags list-import-errors 2>/dev/null | grep -q atlas_batch_pipeline; then
    echo "DAG import error detected:" >&2
    airflow dags list-import-errors >&2 || true
    exit 1
  fi
  sleep 2
done

if ! airflow dags list 2>/dev/null | awk '{print $1}' | grep -qx "atlas_batch_pipeline"; then
  echo "atlas_batch_pipeline not registered. Start Airflow first:" >&2
  echo "  bash scripts/start_airflow_local.sh" >&2
  echo "Check import errors:" >&2
  airflow dags list-import-errors >&2 || true
  exit 1
fi

# The DAG deploys paused by default (Sprint 4); unpause before triggering.
airflow dags unpause atlas_batch_pipeline >/dev/null 2>&1 || true

ARGS=(dags trigger atlas_batch_pipeline -o json)
if [[ -n "$RUN_ID" ]]; then ARGS+=(--run-id "$RUN_ID"); fi
ARGS+=(--conf "$CONF_JSON")
TRIGGER_JSON="$(airflow "${ARGS[@]}")"
DAG_RUN_ID="$(
  TRIGGER_OUT="$TRIGGER_JSON" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ["TRIGGER_OUT"])
if isinstance(payload, list):
    payload = payload[0]
print(payload["dag_run_id"])
PY
)"
echo "Triggered atlas_batch_pipeline run_id=${DAG_RUN_ID} conf=${CONF_JSON}"

report_failed_tasks() {
  echo "Failed or upstream-failed tasks:" >&2
  airflow tasks states-for-dag-run atlas_batch_pipeline "$DAG_RUN_ID" 2>/dev/null \
    | grep -Ei 'failed|upstream_failed' >&2 || echo "  (task states unavailable)" >&2
}

report_audit_row() {
  # Best-effort: report the matching atlas_ops.pipeline_runs row. Requires
  # google-cloud-bigquery credentials; failures here never mask the run result.
  DAG_RUN_ID="$DAG_RUN_ID" ATLAS_PD="$PROCESSING_DATE" python3 - <<'PY' || echo "(audit row lookup unavailable)"
import datetime
import json
import os

from atlas.batch.context import build_pipeline_run_id
from atlas.ops.audit import query_pipeline_run

processing_date = os.environ.get("ATLAS_PD") or datetime.datetime.now(tz=datetime.UTC).date().isoformat()
pipeline_run_id = build_pipeline_run_id(processing_date, os.environ["DAG_RUN_ID"])
row = query_pipeline_run(pipeline_run_id)
if row is None:
    print(f"No audit row found for pipeline_run_id={pipeline_run_id}")
else:
    printable = {k: str(v) for k, v in row.items()}
    print("atlas_ops.pipeline_runs row:")
    print(json.dumps(printable, indent=2))
PY
}

report_summary_path() {
  local summary
  # Prefer the exact summary for this run; fall back to the newest one.
  summary="$(
    DAG_RUN_ID="$DAG_RUN_ID" ATLAS_PD="$PROCESSING_DATE" python3 - <<'PY' 2>/dev/null || true
import datetime
import os

from atlas.batch.context import build_pipeline_run_id
from atlas.config.settings import atlas_root

processing_date = os.environ.get("ATLAS_PD") or datetime.datetime.now(tz=datetime.UTC).date().isoformat()
pipeline_run_id = build_pipeline_run_id(processing_date, os.environ["DAG_RUN_ID"])
path = atlas_root() / "logs" / "airflow" / pipeline_run_id / "run-summary.json"
if path.exists():
    print(path)
PY
  )"
  if [[ -z "$summary" ]]; then
    summary="$(ls -t "${ATLAS_ROOT}"/logs/airflow/*/run-summary.json 2>/dev/null | head -1 || true)"
  fi
  if [[ -n "$summary" ]]; then
    echo "Local run summary: $summary"
  fi
}

echo "Polling run to terminal state (timeout ${RUN_TIMEOUT_SECONDS}s)..."
run_deadline=$((SECONDS + RUN_TIMEOUT_SECONDS))
STATE=""
while (( SECONDS < run_deadline )); do
  STATE="$(airflow dags state atlas_batch_pipeline "$DAG_RUN_ID" -o plain 2>/dev/null | tail -1 | tr -d '[:space:]')"
  case "$STATE" in
    success)
      echo "Airflow final state: success"
      report_audit_row
      report_summary_path
      exit 0
      ;;
    failed)
      echo "Airflow final state: failed" >&2
      report_failed_tasks
      report_audit_row
      report_summary_path
      exit 1
      ;;
  esac
  sleep "$POLL_INTERVAL_SECONDS"
done

echo "Timed out after ${RUN_TIMEOUT_SECONDS}s waiting for run ${DAG_RUN_ID} (last state: ${STATE:-unknown})" >&2
report_failed_tasks
report_audit_row
exit 1
