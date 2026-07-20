#!/usr/bin/env bash
# Shared Airflow + Atlas environment for local and Cloud Shell runs.
set -euo pipefail

ATLAS_ROOT="${ATLAS_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export ATLAS_ROOT
export PYTHONPATH="${ATLAS_ROOT}/src:${ATLAS_ROOT}/dags:${PYTHONPATH:-}"
export AIRFLOW_HOME="${AIRFLOW_HOME:-${ATLAS_ROOT}/.airflow}"
export AIRFLOW__CORE__LOAD_EXAMPLES="${AIRFLOW__CORE__LOAD_EXAMPLES:-False}"
export AIRFLOW__CORE__DAGS_FOLDER="${AIRFLOW__CORE__DAGS_FOLDER:-${ATLAS_ROOT}/dags}"
export DBT_PROJECT_DIR="${DBT_PROJECT_DIR:-${ATLAS_ROOT}/dbt/atlas_dbt}"
export DBT_PROFILES_DIR="${DBT_PROFILES_DIR:-${HOME}/.dbt}"
export ATLAS_GCP_PROJECT_ID="${ATLAS_GCP_PROJECT_ID:-example-gcp-project}"
export ATLAS_GCS_BUCKET="${ATLAS_GCS_BUCKET:-atlas-raw-events-example-gcp-project}"
export ATLAS_BQ_DATASET="${ATLAS_BQ_DATASET:-atlas_raw}"
export ATLAS_DBT_DATASET="${ATLAS_DBT_DATASET:-atlas}"
export DBT_LOCATION="${DBT_LOCATION:-US}"
export GOOGLE_APPLICATION_CREDENTIALS="${GOOGLE_APPLICATION_CREDENTIALS:-${HOME}/.gcp/atlas-service-account.json}"
export PATH="${ATLAS_ROOT}/.venv-dbt/bin:${HOME}/google-cloud-sdk/bin:${HOME}/.local/bin:${PATH}"

if [[ -f "${ATLAS_ROOT}/.venv-airflow/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "${ATLAS_ROOT}/.venv-airflow/bin/activate"
fi
