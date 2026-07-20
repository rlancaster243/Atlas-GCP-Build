#!/usr/bin/env bash
# Configure the isolated Atlas dbt environment and user-level profile.
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

ATLAS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE_ROOT="$(cd "${ATLAS_ROOT}/.." && pwd)"
DBT_ROOT="${ATLAS_ROOT}/dbt"
DBT_PROJECT_DIR="${DBT_ROOT}/atlas_dbt"
REQUIREMENTS_FILE="${DBT_ROOT}/requirements-dbt.txt"
VENV_DIR="${ATLAS_ROOT}/.venv-dbt"
DEFAULT_ATLAS_PROJECT="example-gcp-project"

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

require_command gcloud
require_command bq
require_command git

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
else
  fail "python3 (or python) is required but was not found on PATH"
fi

run "$PYTHON_BIN" --version

print_command git -C "$WORKSPACE_ROOT" rev-parse --show-toplevel
GIT_ROOT="$(git -C "$WORKSPACE_ROOT" rev-parse --show-toplevel)"
[[ "$GIT_ROOT" == "$WORKSPACE_ROOT" ]] \
  || fail "expected ${WORKSPACE_ROOT} to be the git worktree root, found ${GIT_ROOT}"

PROJECT_ID="${ATLAS_GCP_PROJECT_ID:-${GCP_PROJECT_ID:-$DEFAULT_ATLAS_PROJECT}}"
RAW_DATASET="${ATLAS_BQ_DATASET:-atlas_raw}"
TARGET_DATASET="${ATLAS_DBT_DATASET:-atlas}"
AUTH_METHOD="${ATLAS_DBT_AUTH_METHOD:-oauth}"

[[ "$PROJECT_ID" =~ ^[a-z][a-z0-9-]{4,61}[a-z0-9]$ ]] \
  || fail "invalid Atlas GCP project id"
[[ "$RAW_DATASET" =~ ^[A-Za-z_][A-Za-z0-9_]{0,1023}$ ]] \
  || fail "invalid Atlas raw dataset name"
[[ "$TARGET_DATASET" =~ ^[A-Za-z_][A-Za-z0-9_]{0,1023}$ ]] \
  || fail "invalid Atlas dbt target dataset name"

print_command gcloud config get-value project
ACTIVE_PROJECT="$(gcloud config get-value project 2>/dev/null)"
[[ "$ACTIVE_PROJECT" == "$PROJECT_ID" ]] || fail \
  "gcloud project is '${ACTIVE_PROJECT:-unset}', expected '${PROJECT_ID}'; run: gcloud config set project ${PROJECT_ID}"

print_command gcloud projects describe "$PROJECT_ID" --format=value\(projectId\)
DESCRIBED_PROJECT="$(gcloud projects describe "$PROJECT_ID" --format='value(projectId)')"
[[ "$DESCRIBED_PROJECT" == "$PROJECT_ID" ]] \
  || fail "could not verify access to expected GCP project ${PROJECT_ID}"

if [[ -n "${DBT_LOCATION:-}" ]]; then
  LOCATION="$DBT_LOCATION"
  echo "Using DBT_LOCATION=${LOCATION}"
else
  print_command bq "--project_id=${PROJECT_ID}" show --format=json "${PROJECT_ID}:${RAW_DATASET}"
  DATASET_JSON="$(bq "--project_id=${PROJECT_ID}" show --format=json \
    "${PROJECT_ID}:${RAW_DATASET}")"
  LOCATION="$(printf '%s' "$DATASET_JSON" | "$PYTHON_BIN" -c \
    'import json, sys; print(json.load(sys.stdin)["location"])')" \
    || fail "could not discover the ${RAW_DATASET} dataset location"
  [[ -n "$LOCATION" ]] || fail "${RAW_DATASET} did not report a dataset location"
  echo "Discovered ${PROJECT_ID}:${RAW_DATASET} in ${LOCATION}"
fi

[[ "$LOCATION" =~ ^[A-Za-z0-9_-]+$ ]] || fail "invalid BigQuery location"

case "$AUTH_METHOD" in
  oauth)
    ;;
  service-account)
    [[ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" ]] \
      || fail "GOOGLE_APPLICATION_CREDENTIALS is required for service-account auth"
    [[ -f "$GOOGLE_APPLICATION_CREDENTIALS" ]] \
      || fail "GOOGLE_APPLICATION_CREDENTIALS must point to a readable external keyfile"
    [[ -r "$GOOGLE_APPLICATION_CREDENTIALS" ]] \
      || fail "GOOGLE_APPLICATION_CREDENTIALS must point to a readable external keyfile"

    KEYFILE="$("$PYTHON_BIN" -c \
      'import os, sys; print(os.path.realpath(sys.argv[1]))' \
      "$GOOGLE_APPLICATION_CREDENTIALS")"
    case "$KEYFILE" in
      "$WORKSPACE_ROOT"|"$WORKSPACE_ROOT"/*)
        fail "service-account keyfile must be stored outside the git worktree"
        ;;
    esac
    export GOOGLE_APPLICATION_CREDENTIALS="$KEYFILE"
    echo "Using external service-account credentials (contents are not displayed)"
    ;;
  *)
    fail "ATLAS_DBT_AUTH_METHOD must be oauth or service-account"
    ;;
esac

if [[ ! -d "$VENV_DIR" ]]; then
  "$PYTHON_BIN" -c 'import ensurepip' >/dev/null 2>&1 \
    || fail "Python venv support is required (install python3-venv on Debian/Ubuntu)"
  run "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  fail "${VENV_DIR} exists but is not a valid Python virtual environment"
fi
"$VENV_DIR/bin/python" -m pip --version >/dev/null 2>&1 \
  || fail "${VENV_DIR} is incomplete or missing pip; remove it and rerun setup"
echo "Using ${VENV_DIR}"

run "$VENV_DIR/bin/python" -m pip install --upgrade --requirement "$REQUIREMENTS_FILE"
run "$VENV_DIR/bin/dbt" deps --project-dir "$DBT_PROJECT_DIR"

PROFILES_DIR="${DBT_PROFILES_DIR:-$HOME/.dbt}"
[[ -n "$PROFILES_DIR" ]] || fail "DBT_PROFILES_DIR resolved to an empty path"
PROFILE_PATH="${PROFILES_DIR}/profiles.yml"

run mkdir -p "$PROFILES_DIR"
TEMP_PROFILE="$(mktemp "${PROFILES_DIR}/.profiles.yml.XXXXXX")"
cleanup() {
  rm -f "$TEMP_PROFILE"
}
trap cleanup EXIT

if [[ "$AUTH_METHOD" == "oauth" ]]; then
  cat >"$TEMP_PROFILE" <<EOF
atlas_dbt:
  target: dev
  outputs:
    dev:
      type: bigquery
      method: oauth
      project: ${PROJECT_ID}
      dataset: ${TARGET_DATASET}
      location: ${LOCATION}
      threads: 4
      priority: interactive
      job_execution_timeout_seconds: 300
      job_retries: 1
EOF
else
  cat >"$TEMP_PROFILE" <<'EOF'
atlas_dbt:
  target: dev
  outputs:
    dev:
      type: bigquery
      method: service-account
      project: __ATLAS_PROJECT_ID__
      dataset: __ATLAS_TARGET_DATASET__
      location: __ATLAS_LOCATION__
      keyfile: "{{ env_var('GOOGLE_APPLICATION_CREDENTIALS') }}"
      threads: 4
      priority: interactive
      job_execution_timeout_seconds: 300
      job_retries: 1
EOF
  run "$PYTHON_BIN" - "$TEMP_PROFILE" "$PROJECT_ID" "$TARGET_DATASET" "$LOCATION" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
content = path.read_text(encoding="utf-8")
for placeholder, value in zip(
    ("__ATLAS_PROJECT_ID__", "__ATLAS_TARGET_DATASET__", "__ATLAS_LOCATION__"),
    sys.argv[2:],
    strict=True,
):
    content = content.replace(placeholder, value)
path.write_text(content, encoding="utf-8")
PY
fi

run chmod 600 "$TEMP_PROFILE"
run mv -f "$TEMP_PROFILE" "$PROFILE_PATH"
TEMP_PROFILE=""
run chmod 600 "$PROFILE_PATH"
echo "Wrote ${PROFILE_PATH} without displaying credentials"

run "$VENV_DIR/bin/dbt" debug \
  --project-dir "$DBT_PROJECT_DIR" \
  --profiles-dir "$PROFILES_DIR" \
  --target dev

echo "Atlas dbt setup complete. Next commands:"
printf '  source %q\n' "${VENV_DIR}/bin/activate"
printf '  %q deps --project-dir %q\n' "${VENV_DIR}/bin/dbt" "$DBT_PROJECT_DIR"
printf '  %q parse --project-dir %q --profiles-dir %q --target dev\n' \
  "${VENV_DIR}/bin/dbt" "$DBT_PROJECT_DIR" "$PROFILES_DIR"
