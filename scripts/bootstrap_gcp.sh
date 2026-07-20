#!/usr/bin/env bash
# Bootstrap Atlas GCP resources in the sandbox project.
# Requires explicit approval because it mutates cloud infrastructure.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "${ATLAS_APPROVE_PROVISION:-}" != "true" ]]; then
  echo "Refusing to mutate GCP resources without ATLAS_APPROVE_PROVISION=true"
  echo "Review docs/runbook.md, then rerun:"
  echo "  ATLAS_APPROVE_PROVISION=true bash scripts/bootstrap_gcp.sh"
  exit 2
fi

PROJECT_ID="${ATLAS_GCP_PROJECT_ID:-${GCP_PROJECT_ID:-example-gcp-project}}"
LOCATION="${ATLAS_GCP_LOCATION:-US}"
BUCKET="${ATLAS_GCS_BUCKET:-atlas-raw-events-${PROJECT_ID}}"
DATASET="${ATLAS_BQ_DATASET:-atlas_raw}"
TABLE="${ATLAS_BQ_TABLE:-events}"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "error: gcloud is required for bootstrap. Install Google Cloud SDK."
  exit 1
fi

if ! command -v bq >/dev/null 2>&1; then
  echo "error: bq is required for bootstrap. Install Google Cloud SDK."
  exit 1
fi

echo "==> Ensuring GCS bucket gs://${BUCKET}"
if ! gsutil ls -b "gs://${BUCKET}" >/dev/null 2>&1; then
  gsutil mb -p "${PROJECT_ID}" -l "${LOCATION}" "gs://${BUCKET}"
fi

echo "==> Ensuring BigQuery dataset ${DATASET}"
if ! bq --project_id="${PROJECT_ID}" show "${DATASET}" >/dev/null 2>&1; then
  bq --location="${LOCATION}" mk --dataset "${PROJECT_ID}:${DATASET}"
fi

SQL_FILE="${ROOT}/sql/create_events_table.sql"
RENDERED_SQL="$(sed \
  -e "s/{project_id}/${PROJECT_ID}/g" \
  -e "s/{dataset_id}/${DATASET}/g" \
  -e "s/{table_id}/${TABLE}/g" \
  "${SQL_FILE}")"

echo "==> Ensuring BigQuery table ${PROJECT_ID}.${DATASET}.${TABLE}"
echo "${RENDERED_SQL}" | bq query --use_legacy_sql=false

echo "Bootstrap complete."
