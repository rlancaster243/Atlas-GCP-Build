#!/usr/bin/env bash
# Run Sprint 3 live acceptance matrix and print GCP evidence.
set -euo pipefail

ATLAS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "${ATLAS_ROOT}/scripts/airflow_env.sh"

PROJECT_ID="${ATLAS_GCP_PROJECT_ID:-example-gcp-project}"
RESULTS_FILE="${ATLAS_ROOT}/logs/sprint3-acceptance-$(date -u +%Y%m%dT%H%M%SZ).jsonl"
mkdir -p "${ATLAS_ROOT}/logs"

airflow dags unpause atlas_batch_pipeline >/dev/null 2>&1 || true

wait_for_run() {
  local run_id="$1"
  local timeout="${2:-1800}"
  local deadline=$((SECONDS + timeout))
  while (( SECONDS < deadline )); do
    state="$(airflow dags state atlas_batch_pipeline "$run_id" -o plain 2>/dev/null | tail -1 | tr -d '[:space:]')"
    if [[ "$state" == "success" || "$state" == "failed" ]]; then
      echo "$state"
      return 0
    fi
    sleep 10
  done
  echo "timeout"
}

trigger_and_wait() {
  local label="$1"
  local conf="$2"
  local run_id="${3:-}"
  echo ""
  echo "========== ${label} =========="
  local args=(dags trigger atlas_batch_pipeline -c "$conf" -o json)
  if [[ -n "$run_id" ]]; then
    args+=(-r "$run_id")
  fi
  trigger_json="$(airflow "${args[@]}" 2>/dev/null)"
  echo "$trigger_json" | python3 -m json.tool
  actual_run_id="$(echo "$trigger_json" | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['dag_run_id'])")"
  echo "Waiting for run_id=${actual_run_id} ..."
  final_state="$(wait_for_run "$actual_run_id" "${WAIT_SECONDS:-1800}")"
  echo "Airflow final state: ${final_state}"
  echo "$trigger_json" | python3 -c "import json,sys; d=json.load(sys.stdin)[0]; print(json.dumps({'scenario':'$label','dag_run_id':d['dag_run_id'],'logical_date':d.get('logical_date'),'conf':json.loads('$conf'),'airflow_state':'$final_state'}))" >>"$RESULTS_FILE"
}

query_gcp() {
  echo ""
  echo "========== GCP audit (atlas_ops.pipeline_runs) =========="
  bq query --use_legacy_sql=false --format=prettyjson \
    "SELECT pipeline_run_id, batch_id, status, attempt_number, started_at, completed_at
     FROM \`${PROJECT_ID}.atlas_ops.pipeline_runs\`
     ORDER BY started_at DESC
     LIMIT 8"

  echo ""
  echo "========== GCP raw batch counts =========="
  bq query --use_legacy_sql=false --format=pretty \
    "SELECT batch_id, COUNT(*) AS rows, COUNT(DISTINCT pipeline_run_id) AS runs
     FROM \`${PROJECT_ID}.atlas_raw.events\`
     WHERE batch_id IN ('atlas-20260718','atlas-20260701')
     GROUP BY batch_id
     ORDER BY batch_id"

  echo ""
  echo "========== GCS batch objects =========="
  gsutil ls -l "gs://atlas-raw-events-${PROJECT_ID}/raw/event_date=2026-07-18/batch_id=atlas-20260718/**" 2>/dev/null || true
  gsutil ls -l "gs://atlas-raw-events-${PROJECT_ID}/raw/event_date=2026-07-01/batch_id=atlas-20260701/**" 2>/dev/null || true
}

# 1. Retry success (upload_once)
trigger_and_wait "upload_once" \
  '{"processing_date":"2026-07-18","batch_id":"atlas-20260718","upload_once":true}'

# 2. Idempotent rerun (same batch, new pipeline run)
trigger_and_wait "idempotent_rerun" \
  '{"processing_date":"2026-07-18","batch_id":"atlas-20260718"}' \
  "manual__sprint3-idempotent-$(date -u +%Y%m%dT%H%M%SZ)"

# 3. dbt failure injection
trigger_and_wait "dbt_test_failure" \
  '{"processing_date":"2026-07-01","batch_id":"atlas-20260701","dbt_test_failure":true}'

# 4. Historical recovery (backfill without injection)
trigger_and_wait "historical_recovery" \
  '{"processing_date":"2026-07-01","batch_id":"atlas-20260701"}'

query_gcp
echo ""
echo "Scenario results written to ${RESULTS_FILE}"
