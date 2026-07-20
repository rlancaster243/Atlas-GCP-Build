#!/usr/bin/env bash
# Post-deployment smoke validation for Atlas on Composer (Sprint 4, Phase 13).
#
# Usage:
#   validate_atlas_deployment.sh --git-sha <sha> --deployment-id <id>
#       --batch-id <smoke batch> --pipeline-run-id <smoke run> --processing-date <date>
#
# Validates the deployed system, not the upload: a successful upload is not a
# successful deployment. Exits nonzero when any check fails.
set -uo pipefail

ATLAS_SCRIPTS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_atlas_deploy.sh
source "${ATLAS_SCRIPTS_ROOT}/lib_atlas_deploy.sh"
export PYTHONPATH="${ATLAS_SCRIPTS_ROOT}/../src:${PYTHONPATH:-}"

GIT_SHA="" DEPLOYMENT_ID="" BATCH_ID="" PIPELINE_RUN_ID="" PROCESSING_DATE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --git-sha) GIT_SHA="${2:?}"; shift 2 ;;
    --deployment-id) DEPLOYMENT_ID="${2:?}"; shift 2 ;;
    --batch-id) BATCH_ID="${2:?}"; shift 2 ;;
    --pipeline-run-id) PIPELINE_RUN_ID="${2:?}"; shift 2 ;;
    --processing-date) PROCESSING_DATE="${2:?}"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
for required in GIT_SHA BATCH_ID PIPELINE_RUN_ID PROCESSING_DATE; do
  [[ -n "${!required}" ]] || { echo "--${required,,} is required" >&2; exit 2; }
done

EVENTS_BUCKET="${ATLAS_GCS_BUCKET:-atlas-raw-events-${ATLAS_PROJECT_ID}}"
EXPECTED_ROWS=50000
FAILURES=0

check() { # name condition_result message
  local name="$1" ok="$2" message="$3"
  if [[ "$ok" == "0" ]]; then
    echo "[PASS] ${name}: ${message}"
  else
    echo "[FAIL] ${name}: ${message}" >&2
    FAILURES=$((FAILURES + 1))
  fi
}

# --- 1. Expected DAG imported -------------------------------------------------------
DAGS_OUT="$(composer_airflow dags list -o plain || true)"
echo "$DAGS_OUT" | awk '{print $1}' | grep -qx "atlas_batch_pipeline"
check "dag_imported" "$?" "atlas_batch_pipeline present in Composer"

IMPORT_ERRORS="$(composer_airflow dags list-import-errors -o plain || true)"
if echo "$IMPORT_ERRORS" | grep -q "project_atlas"; then
  check "dag_import_errors" 1 "import errors present for project_atlas"
else
  check "dag_import_errors" 0 "no import errors for project_atlas"
fi

# --- 2. Expected git SHA deployed ----------------------------------------------------
BUCKET="$(composer_bucket)"
DEPLOYED_SHA="$(gcloud storage cat "${BUCKET}/data/current/release-manifest.json" 2>/dev/null \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["git_sha"])' || echo "unknown")"
ok=1; [[ "$DEPLOYED_SHA" == "$GIT_SHA" ]] && ok=0
check "deployed_sha" "$ok" "current runtime manifest git_sha=${DEPLOYED_SHA}"

# --- 3. Smoke run reached terminal SUCCESS in Airflow ---------------------------------
# Airflow 3 prints "state, {conf...}" for runs triggered with --conf, so match
# the leading token rather than anchoring the whole line.
RUN_STATE="$(composer_airflow dags state atlas_batch_pipeline "smoke__${DEPLOYMENT_ID}" \
  | grep -Eo '^(success|failed|running|queued)\b' | tail -1 || true)"
ok=1; [[ "$RUN_STATE" == "success" ]] && ok=0
check "airflow_terminal_success" "$ok" "smoke dag run state=${RUN_STATE:-unknown}"

# --- 4-6. Raw batch exists, correct count, no duplicate load ---------------------------
RAW_COUNT="$(bq_scalar "SELECT COUNT(1) FROM \`${ATLAS_PROJECT_ID}.atlas_raw.events\` WHERE batch_id = '${BATCH_ID}'")"
ok=1; [[ "$RAW_COUNT" == "$EXPECTED_ROWS" ]] && ok=0
check "raw_batch_count" "$ok" "raw rows for ${BATCH_ID}: ${RAW_COUNT} (expected ${EXPECTED_ROWS})"

INGESTION_RUNS="$(bq_scalar "SELECT COUNT(DISTINCT pipeline_run_id) FROM \`${ATLAS_PROJECT_ID}.atlas_raw.events\` WHERE batch_id = '${BATCH_ID}'")"
ok=1; [[ "$INGESTION_RUNS" == "1" ]] && ok=0
check "no_duplicate_load" "$ok" "distinct ingestion runs for batch: ${INGESTION_RUNS}"

gcloud storage ls "gs://${EVENTS_BUCKET}/raw/event_date=${PROCESSING_DATE}/batch_id=${BATCH_ID}/events.jsonl" >/dev/null 2>&1
check "gcs_object_exists" "$?" "raw JSONL object present in gs://${EVENTS_BUCKET}"

gcloud storage ls "${BUCKET}/data/current/data/runs/${BATCH_ID}/manifest.json" >/dev/null 2>&1 \
  || gcloud storage ls "${BUCKET}/data/current/data/runs/${BATCH_ID}/" >/dev/null 2>&1
check "batch_manifest_exists" "$?" "batch manifest/artifacts present in Composer data path"

# --- 7. Success marker -------------------------------------------------------------------
gcloud storage ls "${BUCKET}/data/current/data/runs/${BATCH_ID}/success.marker" >/dev/null 2>&1
check "success_marker" "$?" "success.marker present for ${BATCH_ID}"

# --- 8. Warehouse reconciliation (accepted+rejected=raw, facts, marts) ----------------------
python3 "${ATLAS_SCRIPTS_ROOT}/atlas_step_runner.py" validate_warehouse \
  "{\"batch_id\": \"${BATCH_ID}\", \"processing_date\": \"${PROCESSING_DATE}\"}" >/tmp/smoke-warehouse.json
check "warehouse_reconciliation" "$?" "batch-scoped raw/classified/fact/mart reconciliation"

# --- 9. atlas_ops.pipeline_runs SUCCESS row --------------------------------------------------
AUDIT_STATUS="$(bq_scalar "SELECT status FROM \`${ATLAS_PROJECT_ID}.atlas_ops.pipeline_runs\` WHERE pipeline_run_id = '${PIPELINE_RUN_ID}'")"
ok=1; [[ "$AUDIT_STATUS" == "SUCCESS" ]] && ok=0
check "pipeline_runs_success" "$ok" "pipeline_runs status=${AUDIT_STATUS:-missing}"

# --- 10. atlas_ops.deployments references this smoke run --------------------------------------
if [[ -n "$DEPLOYMENT_ID" ]]; then
  DEPLOY_ROW="$(bq_scalar "SELECT COUNT(1) FROM \`${ATLAS_PROJECT_ID}.atlas_ops.deployments\` WHERE deployment_id = '${DEPLOYMENT_ID}'")"
  ok=1; [[ "$DEPLOY_ROW" == "1" ]] && ok=0
  check "deployments_row" "$ok" "atlas_ops.deployments rows for ${DEPLOYMENT_ID}: ${DEPLOY_ROW}"
fi

echo ""
if [[ "$FAILURES" -eq 0 ]]; then
  echo "SMOKE VALIDATION PASSED (git_sha ${GIT_SHA:0:12}, batch ${BATCH_ID})"
  exit 0
fi
echo "SMOKE VALIDATION FAILED: ${FAILURES} check(s) failed" >&2
exit 1
