#!/usr/bin/env bash
# Thin dispatcher over Atlas Python/dbt CLIs with structured context logging.
set -euo pipefail

STEP="${1:?step name required}"
# Note: do NOT use ${2:-{}} — bash parses the default as `{` plus a literal
# trailing `}`, which appends a stray `}` to a JSON object argument and corrupts it.
CTX_JSON="${2:-}"
[[ -n "$CTX_JSON" ]] || CTX_JSON="{}"
ATLAS_ROOT="${ATLAS_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
export ATLAS_ROOT
export PYTHONPATH="${ATLAS_ROOT}/src:${PYTHONPATH:-}"
DBT_PROJECT_DIR="${DBT_PROJECT_DIR:-${ATLAS_ROOT}/dbt/atlas_dbt}"
export DBT_PROJECT_DIR

exec python3 "${ATLAS_ROOT}/scripts/atlas_step_runner.py" "$STEP" "$CTX_JSON"
