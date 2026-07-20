#!/usr/bin/env bash
# Create or reuse local Airflow 3.1.7 environment with Composer-parity pins.
set -euo pipefail

ATLAS_ROOT="${ATLAS_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
VENV="${ATLAS_ROOT}/.venv-airflow"
REQ="${ATLAS_ROOT}/airflow/requirements-airflow.txt"
CONSTRAINTS="https://raw.githubusercontent.com/apache/airflow/constraints-3.1.7/constraints-3.12.txt"
AIRFLOW_HOME="${ATLAS_ROOT}/.airflow"
RESET="${RESET_AIRFLOW:-false}"

if [[ "$RESET" == "true" ]]; then
  rm -rf "$VENV" "$AIRFLOW_HOME"
fi

if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install --upgrade pip
pip install "apache-airflow==3.1.7" --constraint "$CONSTRAINTS"
pip install -r "$REQ"
pip install -r "${ATLAS_ROOT}/requirements.txt" pytest
pip check

export AIRFLOW_HOME
export AIRFLOW__CORE__LOAD_EXAMPLES=False
export AIRFLOW__CORE__DAGS_FOLDER="${ATLAS_ROOT}/dags"
export ATLAS_ROOT
export PYTHONPATH="${ATLAS_ROOT}/src:${ATLAS_ROOT}/dags"
mkdir -p "$AIRFLOW_HOME"

airflow db migrate
airflow info
echo "Airflow setup complete at $VENV"
