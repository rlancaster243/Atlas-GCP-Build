#!/usr/bin/env bash
# Verify BigQuery and dbt MCP prerequisites for desktop and cloud agents.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ATLAS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROJECT_ID="${GCP_PROJECT_ID:-example-gcp-project}"
DBT_BIN="${DBT_PATH:-${ROOT}/.venv/bin/dbt}"

if [[ -n "${ATLAS_GCP_SERVICE_ACCOUNT_KEY:-}" ]]; then
  # Materialize credentials OUTSIDE the git worktree (default ~/.gcp), matching
  # setup_cloud_agent.sh. umask 077 in a subshell closes the window where the
  # file would otherwise be world-readable before chmod.
  KEY_DIR="${ATLAS_CLOUD_KEY_DIR:-${HOME}/.gcp}"
  mkdir -p "${KEY_DIR}"
  KEY_PATH="${KEY_DIR}/atlas-service-account.json"
  ( umask 077; echo "${ATLAS_GCP_SERVICE_ACCOUNT_KEY}" | base64 -d > "${KEY_PATH}" )
  chmod 600 "${KEY_PATH}"
  export GOOGLE_APPLICATION_CREDENTIALS="${KEY_PATH}"
  echo "==> Materialized cloud service account credentials at ${KEY_PATH}"
fi

if [[ ! -x "${DBT_BIN}" ]]; then
  echo "error: dbt executable not found at ${DBT_BIN}"
  exit 1
fi

echo "==> Verifying dbt BigQuery profile"
GCP_PROJECT_ID="${PROJECT_ID}" DBT_TARGET=bigquery "${DBT_BIN}" debug \
  --project-dir "${ROOT}/transform/dbt" \
  --profiles-dir "${ROOT}/transform/dbt"

PYTHON_BIN="${ROOT}/.venv/bin/python"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

echo "==> Verifying BigQuery query access"
"${PYTHON_BIN}" - <<'PY'
from google.cloud import bigquery
import os

project_id = os.environ.get("GCP_PROJECT_ID", "example-gcp-project")
client = bigquery.Client(project=project_id)
rows = list(client.query("SELECT 1 AS ok").result())
assert rows and rows[0]["ok"] == 1
print(f"BigQuery access verified for project {project_id}")
PY

echo "==> Verifying Atlas package imports"
(
  cd "${ATLAS_ROOT}"
  PYTHONPATH="${ATLAS_ROOT}/src" "${PYTHON_BIN}" - <<'PY'
from atlas.config.settings import load_settings
settings = load_settings()
print(f"Atlas settings loaded for project {settings.gcp.project_id}")
PY
)

echo "MCP verification complete."
