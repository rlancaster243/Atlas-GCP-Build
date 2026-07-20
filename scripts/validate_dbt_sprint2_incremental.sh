#!/usr/bin/env bash
# Confirm Sprint 2 incremental idempotency on an unchanged raw source.
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

ATLAS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DBT_PROJECT_DIR="${ATLAS_ROOT}/dbt/atlas_dbt"
VENV_DIR="${ATLAS_ROOT}/.venv-dbt"
PROFILES_DIR="${DBT_PROFILES_DIR:-$HOME/.dbt}"
LOG_DIR="${ATLAS_ROOT}/logs"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT_PATH="${LOG_DIR}/validation-sprint2-incremental-${TIMESTAMP}.json"
PROJECT_ID="${ATLAS_GCP_PROJECT_ID:-${GCP_PROJECT_ID:-}}"

fail() {
  echo "error: $*" >&2
  exit 1
}

print_command() {
  printf '+'
  printf ' %q' "$@"
  printf '\n'
}

run() {
  print_command "$@"
  "$@"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 is required but was not found on PATH"
}

require_command bq
require_command python3
[[ -x "${VENV_DIR}/bin/dbt" ]] || fail "missing ${VENV_DIR}/bin/dbt; run scripts/setup_dbt.sh first"
[[ -n "$PROJECT_ID" ]] || fail "ATLAS_GCP_PROJECT_ID or GCP_PROJECT_ID must be set"

run mkdir -p "$LOG_DIR"
DBT_BIN="${VENV_DIR}/bin/dbt"
DBT_FLAGS=(--project-dir "$DBT_PROJECT_DIR" --profiles-dir "$PROFILES_DIR" --target dev)

run_dbt() {
  run "$DBT_BIN" "$@" "${DBT_FLAGS[@]}"
}

run_query_scalar() {
  local sql="$1"
  bq query --use_legacy_sql=false --format=csv --max_rows=1 --quiet "$sql" | tail -n 1
}

echo "Sprint 2 incremental idempotency check (unchanged raw source expected)"

before_fct="$(run_query_scalar "SELECT COUNT(*) FROM \`${PROJECT_ID}.atlas_core.fct_events\`")"
before_mart="$(run_query_scalar "SELECT COALESCE(SUM(event_count), 0) FROM \`${PROJECT_ID}.atlas_marts.mart_daily_event_metrics\`")"
before_rejected="$(run_query_scalar "SELECT COUNT(*) FROM \`${PROJECT_ID}.atlas_quarantine.int_rejected_events\`")"

echo "Before: fct_events=${before_fct} mart_total=${before_mart} rejected=${before_rejected}"

run_dbt build

after_fct="$(run_query_scalar "SELECT COUNT(*) FROM \`${PROJECT_ID}.atlas_core.fct_events\`")"
after_mart="$(run_query_scalar "SELECT COALESCE(SUM(event_count), 0) FROM \`${PROJECT_ID}.atlas_marts.mart_daily_event_metrics\`")"
after_rejected="$(run_query_scalar "SELECT COUNT(*) FROM \`${PROJECT_ID}.atlas_quarantine.int_rejected_events\`")"

echo "After:  fct_events=${after_fct} mart_total=${after_mart} rejected=${after_rejected}"

overall_status="PASS"
if [[ "$before_fct" != "$after_fct" ]]; then
  echo "[gate] fct_events_row_count_unchanged  FAIL (${before_fct} -> ${after_fct})"
  overall_status="FAIL"
else
  echo "[gate] fct_events_row_count_unchanged  PASS"
fi

if [[ "$before_mart" != "$after_mart" ]]; then
  echo "[gate] mart_event_total_unchanged      FAIL (${before_mart} -> ${after_mart})"
  overall_status="FAIL"
else
  echo "[gate] mart_event_total_unchanged      PASS"
fi

if [[ "$before_rejected" != "$after_rejected" ]]; then
  echo "[gate] rejected_row_count_unchanged    FAIL (${before_rejected} -> ${after_rejected})"
  overall_status="FAIL"
else
  echo "[gate] rejected_row_count_unchanged    PASS"
fi

if run_dbt test --select test_type:singular; then
  echo "[gate] singular_tests                   PASS"
else
  echo "[gate] singular_tests                   FAIL"
  overall_status="FAIL"
fi

export REPORT_PATH PROJECT_ID OVERALL_STATUS="$overall_status"
export BEFORE_FCT="$before_fct" AFTER_FCT="$after_fct"
export BEFORE_MART="$before_mart" AFTER_MART="$after_mart"
export BEFORE_REJECTED="$before_rejected" AFTER_REJECTED="$after_rejected"

python3 - <<'PY'
import json
import os
from datetime import datetime, timezone

report = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "check": "incremental_idempotency",
    "project_id": os.environ["PROJECT_ID"],
    "overall_status": os.environ["OVERALL_STATUS"],
    "counts_before": {
        "fct_events": int(os.environ["BEFORE_FCT"]),
        "mart_event_total": int(os.environ["BEFORE_MART"]),
        "rejected_rows": int(os.environ["BEFORE_REJECTED"]),
    },
    "counts_after": {
        "fct_events": int(os.environ["AFTER_FCT"]),
        "mart_event_total": int(os.environ["AFTER_MART"]),
        "rejected_rows": int(os.environ["AFTER_REJECTED"]),
    },
}
with open(os.environ["REPORT_PATH"], "w", encoding="utf-8") as handle:
    json.dump(report, handle, indent=2)
print(f"Wrote validation report to {os.environ['REPORT_PATH']}")
PY

echo "Overall incremental validation status: ${overall_status}"
if [[ "$overall_status" != "PASS" ]]; then
  exit 1
fi
