#!/usr/bin/env bash
set -euo pipefail
ATLAS_ROOT="${ATLAS_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$ATLAS_ROOT"
# shellcheck disable=SC1091
source "${ATLAS_ROOT}/scripts/airflow_env.sh"

echo "== Shell syntax =="
find scripts -name '*.sh' -print0 | xargs -0 -I{} bash -n {}

echo "== Installing Atlas test dependencies =="
pip install -q -r requirements.txt pytest

echo "== Sprint 1/2/3 unit tests =="
python3 -m pytest tests/unit tests/airflow -q

echo "== DAG import check (when Airflow installed) =="
if command -v airflow >/dev/null 2>&1; then
  import_errors="$(airflow dags list-import-errors 2>/dev/null || true)"
  # Airflow prints "No data found" when there are no import errors; any DAG
  # filepath in the output means at least one module failed to import.
  if grep -qE '\.py' <<<"$import_errors"; then
    echo "FAIL: DAG import errors detected:" >&2
    echo "$import_errors" >&2
    exit 1
  fi
  if ! airflow dags list 2>/dev/null | grep -q atlas_batch_pipeline; then
    echo "FAIL: atlas_batch_pipeline is not registered" >&2
    exit 1
  fi
  echo "atlas_batch_pipeline registered with no import errors"
else
  echo "airflow CLI not installed; DAG registration check skipped (parse-safety pytest gates above still ran)"
fi

echo "Sprint 3 static test gate complete"
