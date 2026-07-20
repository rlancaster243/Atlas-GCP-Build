#!/usr/bin/env bash
# Validate Atlas Sprint 2 dbt outputs and emit timestamped JSON evidence.
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

ATLAS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DBT_PROJECT_DIR="${ATLAS_ROOT}/dbt/atlas_dbt"
VENV_DIR="${ATLAS_ROOT}/.venv-dbt"
PROFILES_DIR="${DBT_PROFILES_DIR:-$HOME/.dbt}"
LOG_DIR="${ATLAS_ROOT}/logs"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT_PATH="${LOG_DIR}/validation-sprint2-${TIMESTAMP}.json"
VALIDATED_RUN_ID="${ATLAS_VALIDATED_RUN_ID:-atlas-20260714T163527Z-19a0e4f6}"
PROJECT_ID="${ATLAS_GCP_PROJECT_ID:-${GCP_PROJECT_ID:-}}"
LOCATION="${DBT_LOCATION:-US}"

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

overall_status="PASS"

record_gate() {
  local name="$1"
  local status="$2"
  if [[ "$status" != "PASS" ]]; then
    overall_status="FAIL"
  fi
  printf '[gate] %-40s %s\n' "$name" "$status"
}

run_query_scalar() {
  local sql="$1"
  bq query --use_legacy_sql=false --format=csv --max_rows=1 --quiet "$sql" | tail -n 1
}

echo "Running Sprint 2 validation for run_id=${VALIDATED_RUN_ID}"

if run_dbt test --select test_type:singular; then
  record_gate "singular_tests" "PASS"
else
  record_gate "singular_tests" "FAIL"
fi

if run_dbt test --exclude test_type:singular; then
  record_gate "generic_and_unit_tests" "PASS"
else
  record_gate "generic_and_unit_tests" "FAIL"
fi

raw_rows="$(run_query_scalar "SELECT COUNT(*) FROM \`${PROJECT_ID}.atlas_raw.events\` WHERE pipeline_run_id = '${VALIDATED_RUN_ID}'")"
accepted_rows="$(run_query_scalar "SELECT COUNT(*) FROM \`${PROJECT_ID}.atlas_intermediate.int_accepted_events\` WHERE pipeline_run_id = '${VALIDATED_RUN_ID}'")"
rejected_rows="$(run_query_scalar "SELECT COUNT(*) FROM \`${PROJECT_ID}.atlas_quarantine.int_rejected_events\` WHERE pipeline_run_id = '${VALIDATED_RUN_ID}'")"
fact_rows="$(run_query_scalar "SELECT COUNT(*) FROM \`${PROJECT_ID}.atlas_core.fct_events\`")"
mart_rows="$(run_query_scalar "SELECT COALESCE(SUM(event_count), 0) FROM \`${PROJECT_ID}.atlas_marts.mart_daily_event_metrics\`")"

if [[ "$raw_rows" == "$((accepted_rows + rejected_rows))" ]]; then
  record_gate "raw_accepted_rejected_reconciliation" "PASS"
else
  record_gate "raw_accepted_rejected_reconciliation" "FAIL"
fi

if [[ "$fact_rows" == "$mart_rows" ]]; then
  record_gate "fact_mart_reconciliation" "PASS"
else
  record_gate "fact_mart_reconciliation" "FAIL"
fi

duplicate_extra="$(run_query_scalar "SELECT COUNTIF(is_duplicate_extra) FROM \`${PROJECT_ID}.atlas_intermediate.int_event_classification\` WHERE pipeline_run_id = '${VALIDATED_RUN_ID}'")"
null_users="$(run_query_scalar "SELECT COUNTIF(user_id IS NULL) FROM \`${PROJECT_ID}.atlas_intermediate.int_event_classification\` WHERE pipeline_run_id = '${VALIDATED_RUN_ID}'")"
invalid_countries="$(run_query_scalar "SELECT COUNTIF(NOT is_valid_country) FROM \`${PROJECT_ID}.atlas_intermediate.int_event_classification\` WHERE pipeline_run_id = '${VALIDATED_RUN_ID}'")"
future_dated="$(run_query_scalar "SELECT COUNTIF(is_future_dated) FROM \`${PROJECT_ID}.atlas_intermediate.int_event_classification\` WHERE pipeline_run_id = '${VALIDATED_RUN_ID}'")"
event_time_late="$(run_query_scalar "SELECT COUNTIF(is_event_time_late_arriving) FROM \`${PROJECT_ID}.atlas_intermediate.int_event_classification\` WHERE pipeline_run_id = '${VALIDATED_RUN_ID}'")"
backdated="$(run_query_scalar "SELECT COUNTIF(is_backdated_event_date) FROM \`${PROJECT_ID}.atlas_intermediate.int_event_classification\` WHERE pipeline_run_id = '${VALIDATED_RUN_ID}'")"
mismatch="$(run_query_scalar "SELECT COUNTIF(has_event_date_timestamp_mismatch) FROM \`${PROJECT_ID}.atlas_intermediate.int_event_classification\` WHERE pipeline_run_id = '${VALIDATED_RUN_ID}'")"

check_anomaly() {
  local name="$1"
  local expected="$2"
  local actual="$3"
  if [[ "$expected" == "$actual" ]]; then
    record_gate "anomaly_${name}" "PASS"
  else
    record_gate "anomaly_${name}" "FAIL"
  fi
}

check_anomaly "duplicate_extra" 50 "$duplicate_extra"
check_anomaly "null_users" 500 "$null_users"
check_anomaly "invalid_countries" 200 "$invalid_countries"
check_anomaly "future_dated" 150 "$future_dated"
check_anomaly "event_time_late" 0 "$event_time_late"
check_anomaly "backdated_event_date" 300 "$backdated"
check_anomaly "date_timestamp_mismatch" 300 "$mismatch"

export VALIDATED_RUN_ID PROJECT_ID LOCATION OVERALL_STATUS="$overall_status" REPORT_PATH
export RAW_ROWS="$raw_rows" ACCEPTED_ROWS="$accepted_rows" REJECTED_ROWS="$rejected_rows"
export FACT_ROWS="$fact_rows" MART_ROWS="$mart_rows"
export DUPLICATE_EXTRA="$duplicate_extra" NULL_USERS="$null_users"
export INVALID_COUNTRIES="$invalid_countries" FUTURE_DATED="$future_dated"
export EVENT_TIME_LATE="$event_time_late" BACKDATED="$backdated" MISMATCH="$mismatch"

python3 - <<'PY'
import json
import os
from datetime import datetime, timezone

report = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "validated_run_id": os.environ["VALIDATED_RUN_ID"],
    "project_id": os.environ["PROJECT_ID"],
    "location": os.environ["LOCATION"],
    "overall_status": os.environ["OVERALL_STATUS"],
    "counts": {
        "raw_rows": int(os.environ["RAW_ROWS"]),
        "accepted_rows": int(os.environ["ACCEPTED_ROWS"]),
        "rejected_rows": int(os.environ["REJECTED_ROWS"]),
        "fact_rows": int(os.environ["FACT_ROWS"]),
        "mart_event_total": int(os.environ["MART_ROWS"]),
    },
    "anomalies": {
        "duplicate_extra": int(os.environ["DUPLICATE_EXTRA"]),
        "null_users": int(os.environ["NULL_USERS"]),
        "invalid_countries": int(os.environ["INVALID_COUNTRIES"]),
        "future_dated": int(os.environ["FUTURE_DATED"]),
        "event_time_late_arriving": int(os.environ["EVENT_TIME_LATE"]),
        "backdated_event_date": int(os.environ["BACKDATED"]),
        "date_timestamp_mismatch": int(os.environ["MISMATCH"]),
    },
}
with open(os.environ["REPORT_PATH"], "w", encoding="utf-8") as handle:
    json.dump(report, handle, indent=2)
print(f"Wrote validation report to {os.environ['REPORT_PATH']}")
PY

echo "Overall validation status: ${overall_status}"
if [[ "$overall_status" != "PASS" ]]; then
  exit 1
fi
