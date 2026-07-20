#!/usr/bin/env bash
# Run the Atlas Sprint 2 dbt warehouse build in Cloud Shell or an approved agent env.
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

ATLAS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DBT_PROJECT_DIR="${ATLAS_ROOT}/dbt/atlas_dbt"
VENV_DIR="${ATLAS_ROOT}/.venv-dbt"
PROFILES_DIR="${DBT_PROFILES_DIR:-$HOME/.dbt}"
LOG_DIR="${ATLAS_ROOT}/logs"
ARTIFACT_DIR="${LOG_DIR}/dbt-artifacts"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"

FULL_REFRESH=false
SKIP_DOCS=false

usage() {
  cat <<'EOF'
Usage: run_dbt_sprint2.sh [--full-refresh] [--skip-docs]

Runs deps, debug, seed, source freshness, build, optional docs generation,
and preserves dbt artifacts under logs/dbt-artifacts/.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --full-refresh)
      FULL_REFRESH=true
      shift
      ;;
    --skip-docs)
      SKIP_DOCS=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

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
[[ -x "${VENV_DIR}/bin/dbt" ]] || fail "missing ${VENV_DIR}/bin/dbt; run scripts/setup_dbt.sh first"

run mkdir -p "$LOG_DIR" "$ARTIFACT_DIR"
DBT_BIN="${VENV_DIR}/bin/dbt"
DBT_FLAGS=(--project-dir "$DBT_PROJECT_DIR" --profiles-dir "$PROFILES_DIR" --target dev)

run_dbt() {
  run "$DBT_BIN" "$@" "${DBT_FLAGS[@]}"
}

run_dbt deps
run_dbt debug
run_dbt seed --full-refresh
run_dbt source freshness || true

if [[ "$FULL_REFRESH" == true ]]; then
  run_dbt build --full-refresh
else
  run_dbt build
fi

if [[ "$SKIP_DOCS" == false ]]; then
  run_dbt docs generate
  run mkdir -p "${ARTIFACT_DIR}/${TIMESTAMP}"
  run cp -a "${DBT_PROJECT_DIR}/target/." "${ARTIFACT_DIR}/${TIMESTAMP}/"
fi

PROJECT_ID="${ATLAS_GCP_PROJECT_ID:-${GCP_PROJECT_ID:-}}"
[[ -n "$PROJECT_ID" ]] || fail "ATLAS_GCP_PROJECT_ID or GCP_PROJECT_ID must be set"
BQ_REGION="$(printf '%s' "${DBT_LOCATION:-US}" | tr '[:upper:]' '[:lower:]')"

print_inventory() {
  local dataset="$1"
  local table="$2"
  bq query --use_legacy_sql=false --format=prettyjson \
    "SELECT table_schema, table_name, table_type
     FROM \`${PROJECT_ID}.region-${BQ_REGION}.INFORMATION_SCHEMA.TABLES\`
     WHERE table_schema = '${dataset}' AND table_name = '${table}'" 2>/dev/null || true
}

echo "Sprint 2 relation inventory (best effort):"
for relation in \
  "atlas_staging.stg_events" \
  "atlas_intermediate.int_event_classification" \
  "atlas_intermediate.int_accepted_events" \
  "atlas_quarantine.int_rejected_events" \
  "atlas_core.fct_events" \
  "atlas_marts.mart_daily_event_metrics"
do
  schema="${relation%%.*}"
  table="${relation##*.}"
  echo "- ${PROJECT_ID}.${relation}"
  print_inventory "$schema" "$table"
done

run_dbt show --select stg_events --limit 1
echo "dbt Sprint 2 run complete. Artifacts: ${ARTIFACT_DIR}/${TIMESTAMP}/"
echo "Next: bash scripts/validate_dbt_sprint2.sh"
