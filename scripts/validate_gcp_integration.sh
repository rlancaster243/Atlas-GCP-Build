#!/usr/bin/env bash
# Isolated GCP integration test for Project Atlas (Sprint 4, Phase 7).
#
# Runs the full pipeline against ephemeral, run-scoped resources:
#   raw dataset:   atlas_ci_<run>_raw
#   dbt datasets:  atlas_ci_<run>_{staging,intermediate,core,marts,quarantine}
#   GCS prefix:    gs://<CI bucket>/atlas-ci/<run>/
#
# Never touches canonical Atlas datasets or the canonical events bucket.
# Cleanup always runs (EXIT trap); failures are recorded and fail the script.
# Orphan recovery (TTL): the CI bucket auto-deletes objects after 7 days;
# stale datasets can be listed with
#   bq ls --project_id <project> | grep atlas_ci_
# and removed with `bq rm -r -f -d <project>:<dataset>`.
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
ATLAS_DIR="$(pwd)"

RUN_TOKEN="${GITHUB_RUN_ID:-local$(date -u +%s)}"
RUN_TOKEN="${RUN_TOKEN//[^a-zA-Z0-9]/}"
export ATLAS_GCP_PROJECT_ID="${ATLAS_GCP_PROJECT_ID:-example-gcp-project}"
export ATLAS_GCS_BUCKET="${ATLAS_CI_BUCKET:-atlas-ci-${ATLAS_GCP_PROJECT_ID}}"
export ATLAS_GCS_PREFIX="atlas-ci/${RUN_TOKEN}/raw"
export ATLAS_BQ_DATASET="atlas_ci_${RUN_TOKEN}_raw"
export ATLAS_DBT_DATASET="atlas_ci_${RUN_TOKEN}"
export DBT_LOCATION="${DBT_LOCATION:-US}"

BATCH_ID="atlas-ci-${RUN_TOKEN}"
PIPELINE_RUN_ID="atlas-ci-run-${RUN_TOKEN}"
PROCESSING_DATE="${ATLAS_CI_PROCESSING_DATE:-$(date -u +%F)}"
EXPECTED_ROWS=50000
PY="${ATLAS_PYTHON:-python3}"
export PYTHONPATH="${ATLAS_DIR}/src:${PYTHONPATH:-}"

RESULTS_DIR="${ATLAS_DIR}/logs/ci"
RESULTS_FILE="${RESULTS_DIR}/integration-results.json"
mkdir -p "$RESULTS_DIR"
declare -a GATE_NAMES=() GATE_STATUSES=()
OVERALL=0

record() { # name status
  GATE_NAMES+=("$1")
  GATE_STATUSES+=("$2")
  if [[ "$2" == "FAIL" ]]; then OVERALL=1; fi
  printf '[%s] %s\n' "$2" "$1"
}

run_gate() { # name command...
  local name="$1"
  shift
  echo ""
  echo "=== gate: ${name} ==="
  if "$@"; then record "$name" "PASS"; else record "$name" "FAIL"; fi
}

write_results() {
  {
    echo '{'
    echo "  \"run_token\": \"${RUN_TOKEN}\","
    echo "  \"batch_id\": \"${BATCH_ID}\","
    echo "  \"raw_dataset\": \"${ATLAS_BQ_DATASET}\","
    echo "  \"dbt_dataset_prefix\": \"${ATLAS_DBT_DATASET}\","
    echo "  \"gcs_prefix\": \"gs://${ATLAS_GCS_BUCKET}/atlas-ci/${RUN_TOKEN}/\","
    echo '  "gates": ['
    local i
    for i in "${!GATE_NAMES[@]}"; do
      local sep=','
      [[ "$i" -eq $((${#GATE_NAMES[@]} - 1)) ]] && sep=''
      echo "    {\"name\": \"${GATE_NAMES[$i]}\", \"status\": \"${GATE_STATUSES[$i]}\"}${sep}"
    done
    echo '  ],'
    if [[ "$OVERALL" -eq 0 ]]; then
      echo '  "overall": "PASS"'
    else
      echo '  "overall": "FAIL"'
    fi
    echo '}'
  } >"$RESULTS_FILE"
  echo ""
  echo "Results written to ${RESULTS_FILE}"
}

# --- Cleanup (always runs) -----------------------------------------------------
CLEANED=0
cleanup() {
  if [[ "$CLEANED" -eq 1 ]]; then return; fi
  CLEANED=1
  echo ""
  echo "=== cleanup: removing ephemeral resources for run ${RUN_TOKEN} ==="
  local cleanup_failed=0
  local ds
  for ds in \
    "${ATLAS_BQ_DATASET}" \
    "${ATLAS_DBT_DATASET}" \
    "${ATLAS_DBT_DATASET}_staging" \
    "${ATLAS_DBT_DATASET}_intermediate" \
    "${ATLAS_DBT_DATASET}_core" \
    "${ATLAS_DBT_DATASET}_marts" \
    "${ATLAS_DBT_DATASET}_quarantine"; do
    if bq --project_id="$ATLAS_GCP_PROJECT_ID" show --dataset "$ds" >/dev/null 2>&1; then
      if bq --project_id="$ATLAS_GCP_PROJECT_ID" rm -r -f -d "$ds" >/dev/null 2>&1; then
        echo "  deleted dataset ${ds}"
      else
        echo "  FAILED to delete dataset ${ds}"
        cleanup_failed=1
      fi
    fi
  done
  if gcloud storage ls "gs://${ATLAS_GCS_BUCKET}/atlas-ci/${RUN_TOKEN}/" >/dev/null 2>&1; then
    if gcloud storage rm -r "gs://${ATLAS_GCS_BUCKET}/atlas-ci/${RUN_TOKEN}/**" >/dev/null 2>&1; then
      echo "  deleted gs://${ATLAS_GCS_BUCKET}/atlas-ci/${RUN_TOKEN}/"
    else
      echo "  FAILED to delete gs://${ATLAS_GCS_BUCKET}/atlas-ci/${RUN_TOKEN}/ (7-day TTL will reap it)"
      cleanup_failed=1
    fi
  fi
  # Verify nothing scoped to this run remains.
  local leftovers
  leftovers="$(bq --project_id="$ATLAS_GCP_PROJECT_ID" ls --max_results=1000 2>/dev/null | grep -c "atlas_ci_${RUN_TOKEN}" || true)"
  if [[ "$leftovers" != "0" ]]; then
    echo "  cleanup verification FAILED: ${leftovers} dataset(s) remain for run ${RUN_TOKEN}"
    cleanup_failed=1
  else
    echo "  cleanup verified: no atlas_ci_${RUN_TOKEN}* datasets remain"
  fi
  if [[ "$cleanup_failed" -eq 1 ]]; then
    record "cleanup" "FAIL"
  else
    record "cleanup" "PASS"
  fi
  write_results
}
trap cleanup EXIT

echo "Isolated integration run"
echo "  project:        ${ATLAS_GCP_PROJECT_ID}"
echo "  run token:      ${RUN_TOKEN}"
echo "  raw dataset:    ${ATLAS_BQ_DATASET}"
echo "  dbt datasets:   ${ATLAS_DBT_DATASET}_{staging,intermediate,core,marts,quarantine}"
echo "  gcs prefix:     gs://${ATLAS_GCS_BUCKET}/${ATLAS_GCS_PREFIX}"
echo "  batch id:       ${BATCH_ID}"

# --- 1. Authentication and API reachability -------------------------------------
gate_auth() {
  local identity
  identity="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null)" || return 1
  [[ -n "$identity" ]] || { echo "no active gcloud identity"; return 1; }
  echo "active identity: ${identity}"
  bq --project_id="$ATLAS_GCP_PROJECT_ID" query --use_legacy_sql=false --format=none 'SELECT 1' || return 1
  gcloud storage ls "gs://${ATLAS_GCS_BUCKET}/" >/dev/null || return 1
  echo "BigQuery and GCS reachable"
}
run_gate "auth_and_apis" gate_auth

# --- 2. Migration validation (plan mode, no mutation) ----------------------------
gate_migration_plan() {
  bash "${ATLAS_DIR}/scripts/apply_atlas_migrations.sh" --mode plan
}
if [[ -f "${ATLAS_DIR}/scripts/apply_atlas_migrations.sh" ]]; then
  run_gate "migration_plan" gate_migration_plan
else
  record "migration_plan" "SKIP"
fi

# --- 3. Deterministic generation --------------------------------------------------
GEN_DIR="$(mktemp -d)"
gate_generation() {
  local out1 out2 sum1 sum2
  out1="$("$PY" "${ATLAS_DIR}/scripts/generate_events.py" \
    --processing-date "$PROCESSING_DATE" --batch-id "$BATCH_ID" \
    --pipeline-run-id "$PIPELINE_RUN_ID" --seed 42 \
    --output-path "${GEN_DIR}/events-a.jsonl")" || return 1
  out2="$("$PY" "${ATLAS_DIR}/scripts/generate_events.py" \
    --processing-date "$PROCESSING_DATE" --batch-id "$BATCH_ID" \
    --pipeline-run-id "$PIPELINE_RUN_ID" --seed 42 \
    --output-path "${GEN_DIR}/events-b.jsonl")" || return 1
  sum1="$(echo "$out1" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["checksum_sha256"])')"
  sum2="$(echo "$out2" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["checksum_sha256"])')"
  echo "checksum A: ${sum1}"
  echo "checksum B: ${sum2}"
  [[ -n "$sum1" && "$sum1" == "$sum2" ]] || { echo "generation is not deterministic"; return 1; }
}
run_gate "deterministic_generation" gate_generation

# --- 4. Upload to isolated GCS prefix ---------------------------------------------
gate_upload() {
  "$PY" "${ATLAS_DIR}/scripts/upload_events.py" \
    --local-path "${GEN_DIR}/events-a.jsonl" \
    --event-date "$PROCESSING_DATE" \
    --run-id "$PIPELINE_RUN_ID" \
    --batch-id "$BATCH_ID"
}
run_gate "gcs_upload" gate_upload

GCS_URI="gs://${ATLAS_GCS_BUCKET}/${ATLAS_GCS_PREFIX}/event_date=${PROCESSING_DATE}/batch_id=${BATCH_ID}/events.jsonl"

# --- 5. Raw load into isolated dataset ---------------------------------------------
gate_raw_load() {
  "$PY" "${ATLAS_DIR}/scripts/load_events.py" \
    --gcs-uri "$GCS_URI" --run-id "$PIPELINE_RUN_ID" \
    --batch-id "$BATCH_ID" --processing-date "$PROCESSING_DATE" \
    --expected-row-count "$EXPECTED_ROWS"
}
run_gate "raw_load" gate_raw_load

# --- 6. Idempotent rerun: second load must skip, count must not change ---------------
gate_idempotent_rerun() {
  local rerun already rows
  rerun="$("$PY" "${ATLAS_DIR}/scripts/load_events.py" \
    --gcs-uri "$GCS_URI" --run-id "${PIPELINE_RUN_ID}-rerun" \
    --batch-id "$BATCH_ID" --processing-date "$PROCESSING_DATE" \
    --expected-row-count "$EXPECTED_ROWS")" || return 1
  already="$(echo "$rerun" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["already_loaded"])')"
  [[ "$already" == "True" ]] || { echo "rerun did not skip (already_loaded=${already})"; return 1; }
  rows="$(bq --project_id="$ATLAS_GCP_PROJECT_ID" query --use_legacy_sql=false --format=csv \
    "SELECT COUNT(1) FROM \`${ATLAS_GCP_PROJECT_ID}.${ATLAS_BQ_DATASET}.events\` WHERE batch_id = '${BATCH_ID}'" \
    | tail -1)"
  echo "raw rows after rerun: ${rows}"
  [[ "$rows" == "$EXPECTED_ROWS" ]] || { echo "duplicate rows detected"; return 1; }
}
run_gate "idempotent_rerun" gate_idempotent_rerun

# --- 7. dbt build against isolated schemas -------------------------------------------
DBT_DIR="${ATLAS_DIR}/dbt/atlas_dbt"
DBT_PROFILES_TMP="$(mktemp -d)"
cp "${DBT_DIR}/profiles.yml.example" "${DBT_PROFILES_TMP}/profiles.yml"
gate_dbt_build() {
  (cd "$DBT_DIR" \
    && dbt deps --profiles-dir "$DBT_PROFILES_TMP" --quiet \
    && dbt build --profiles-dir "$DBT_PROFILES_TMP" \
      --vars "{\"validated_batch_id\": \"${BATCH_ID}\"}")
}
run_gate "dbt_build_isolated" gate_dbt_build

# --- 8. Batch-scoped warehouse reconciliation -----------------------------------------
gate_reconciliation() {
  "$PY" "${ATLAS_DIR}/scripts/atlas_step_runner.py" validate_warehouse \
    "{\"batch_id\": \"${BATCH_ID}\", \"processing_date\": \"${PROCESSING_DATE}\"}"
}
run_gate "warehouse_reconciliation" gate_reconciliation

echo ""
echo "=== integration gates complete (cleanup follows) ==="
cleanup
trap - EXIT
exit "$OVERALL"
