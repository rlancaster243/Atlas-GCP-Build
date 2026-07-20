#!/usr/bin/env bash
# Build an immutable, checksum-verified Atlas deployment bundle (Sprint 4, Phase 8).
#
# Usage:
#   build_deployment_bundle.sh [--upload] [--environment atlas-dev]
#
# Produces dist/atlas-bundle-<git_sha>.tar.gz + release-manifest.json.
# With --upload, stores the bundle create-only under
#   gs://<ATLAS_DEPLOYMENT_BUCKET>/atlas/releases/<git_sha>/
# Reuse is allowed only on exact checksum match; a different checksum for an
# existing release path is a hard failure (never overwrite).
#
# Determinism note: tar/gzip metadata is normalized (sorted names, fixed
# mtime, gzip -n), so archive bytes depend only on file content. The manifest
# intentionally embeds build metadata (timestamp, builder, workflow run), so
# rebuilding the same git SHA in a new context yields a different checksum.
# Deployment tooling must therefore REUSE an existing stored release for a SHA
# instead of rebuilding it; the create-only check above enforces this.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
ATLAS_DIR="$(pwd)"
PY="${ATLAS_PYTHON:-python3}"
PROJECT_ID="${ATLAS_GCP_PROJECT_ID:-example-gcp-project}"
DEPLOYMENT_BUCKET="${ATLAS_DEPLOYMENT_BUCKET:-atlas-deployments-${PROJECT_ID}}"
ENVIRONMENT="atlas-dev"
UPLOAD=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --upload) UPLOAD=1; shift ;;
    --environment) ENVIRONMENT="${2:?}"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

GIT_SHA="$(git rev-parse HEAD)"
GIT_REF="$(git rev-parse --abbrev-ref HEAD)"
RELEASE_TAG="$(git describe --tags --exact-match 2>/dev/null || echo "")"
if [[ -n "$(git status --porcelain -- project-atlas 2>/dev/null || true)" ]]; then
  echo "WARNING: working tree has uncommitted project-atlas changes; bundle records HEAD ${GIT_SHA:0:12}" >&2
fi

DIST_DIR="${ATLAS_DIR}/dist"
STAGE_DIR="$(mktemp -d)"
BUNDLE_ROOT="${STAGE_DIR}/atlas-bundle"
mkdir -p "$DIST_DIR" "$BUNDLE_ROOT"
trap 'rm -rf "$STAGE_DIR"' EXIT

# --- Stage runtime assets only ---------------------------------------------------
copy() { # src dest-subdir
  local src="$1" dest="${BUNDLE_ROOT}/$2"
  mkdir -p "$(dirname "$dest")"
  cp -r "$src" "$dest"
}

copy dags dags
copy src/atlas src/atlas
copy config config
copy sql sql
copy dbt/atlas_dbt dbt/atlas_dbt
copy scripts/atlas_step_runner.py scripts/atlas_step_runner.py
copy scripts/run_atlas_step.sh scripts/run_atlas_step.sh
copy scripts/generate_events.py scripts/generate_events.py
copy scripts/upload_events.py scripts/upload_events.py
copy scripts/load_events.py scripts/load_events.py
copy scripts/validate_events.py scripts/validate_events.py
copy scripts/apply_atlas_migrations.sh scripts/apply_atlas_migrations.sh
# Sprint 5 observability runtime assets: metric catalog and schema manifest
# are loaded at runtime by atlas.observability.{metrics,schema_drift}.
copy observability/metrics observability/metrics
copy observability/schema observability/schema
# Runtime dbt profile: keyless oauth via the environment's service account.
mkdir -p "${BUNDLE_ROOT}/dbt/profiles"
cp dbt/atlas_dbt/profiles.yml.example "${BUNDLE_ROOT}/dbt/profiles/profiles.yml"
copy requirements.txt requirements.txt
copy airflow/requirements-airflow.txt airflow/requirements-airflow.txt
copy dbt/requirements-dbt.txt dbt/requirements-dbt.txt

# Strip anything that must never ship: caches, local state, dbt build outputs.
find "$BUNDLE_ROOT" \( -name '__pycache__' -o -name '.pytest_cache' -o -name '.mypy_cache' \) \
  -type d -prune -exec rm -rf {} +
rm -rf "$BUNDLE_ROOT/dbt/atlas_dbt/target" "$BUNDLE_ROOT/dbt/atlas_dbt/logs" \
  "$BUNDLE_ROOT/dbt/atlas_dbt/dbt_packages"
find "$BUNDLE_ROOT" -name '*.pyc' -delete

# Vendor pinned dbt packages so the bundle is self-contained at runtime.
# Composer workers must never resolve packages from the network; deployment
# atlas-dev-20260718T233128Z-74732eee failed at dbt_seed because dbt_packages
# was stripped and no runtime `dbt deps` exists by design. package-lock.yml
# pins exact versions, keeping the vendored tree reproducible.
if ! command -v dbt >/dev/null 2>&1; then
  echo "FATAL: dbt CLI required to vendor dbt_packages into the bundle" >&2
  exit 1
fi
(
  cd "$BUNDLE_ROOT/dbt/atlas_dbt"
  ATLAS_GCP_PROJECT_ID="${ATLAS_GCP_PROJECT_ID:-bundle-build-placeholder}" \
    ATLAS_DBT_DATASET="${ATLAS_DBT_DATASET:-atlas_dbt}" \
    DBT_TARGET_PATH=/tmp/atlas-bundle-dbt-target DBT_LOG_PATH=/tmp/atlas-bundle-dbt-logs \
    dbt deps --profiles-dir ../profiles >/dev/null
)
rm -rf /tmp/atlas-bundle-dbt-target /tmp/atlas-bundle-dbt-logs
find "$BUNDLE_ROOT/dbt/atlas_dbt/dbt_packages" \( -name '__pycache__' -o -name '.git' \) \
  -prune -exec rm -rf {} + 2>/dev/null || true
if [[ ! -d "$BUNDLE_ROOT/dbt/atlas_dbt/dbt_packages/dbt_utils" ]]; then
  echo "FATAL: dbt_packages/dbt_utils missing after vendoring" >&2
  exit 1
fi

# Refuse to bundle anything that resembles real credential material. Patterns
# target actual PEM blocks and populated key fields, not detector source code
# that merely mentions the field names.
if grep -rlE -- '-----BEGIN [A-Z ]*PRIVATE KEY-----|"private_key"[[:space:]]*:[[:space:]]*"[^"]+"' \
    "$BUNDLE_ROOT" >/dev/null 2>&1; then
  grep -rlE -- '-----BEGIN [A-Z ]*PRIVATE KEY-----|"private_key"[[:space:]]*:[[:space:]]*"[^"]+"' "$BUNDLE_ROOT" >&2
  echo "FATAL: credential-like content detected in bundle staging; aborting." >&2
  exit 1
fi

# --- Release manifest -------------------------------------------------------------
export BUNDLE_ROOT GIT_SHA GIT_REF RELEASE_TAG ENVIRONMENT
"$PY" - <<'PY'
import hashlib
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

bundle_root = Path(os.environ["BUNDLE_ROOT"])

def pin(path: str, name: str) -> str | None:
    text = Path(path).read_text(encoding="utf-8")
    m = re.search(rf"^{re.escape(name)}==(\S+)", text, re.MULTILINE)
    return m.group(1) if m else None

files = sorted(p for p in bundle_root.rglob("*") if p.is_file())
checksums = {
    str(p.relative_to(bundle_root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
}

manifest_lines = [
    line.split("|")[0].strip()
    for line in (bundle_root / "sql/migrations/manifest.txt").read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.startswith("#")
]

manifest = {
    "git_sha": os.environ["GIT_SHA"],
    "git_ref": os.environ["GIT_REF"],
    "release_tag": os.environ.get("RELEASE_TAG") or None,
    "build_timestamp": datetime.now(tz=UTC).isoformat(),
    "builder": os.environ.get("GITHUB_ACTOR") or os.environ.get("USER") or "unknown",
    "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
    "python_version": subprocess.check_output(["python3", "--version"], text=True).strip(),
    "airflow_version": pin("airflow/requirements-airflow.txt", "apache-airflow"),
    "provider_versions": {
        "apache-airflow-providers-google": pin(
            "airflow/requirements-airflow.txt", "apache-airflow-providers-google"
        ),
        "apache-airflow-providers-standard": pin(
            "airflow/requirements-airflow.txt", "apache-airflow-providers-standard"
        ),
    },
    "dbt_versions": {
        "dbt-core": pin("dbt/requirements-dbt.txt", "dbt-core"),
        "dbt-bigquery": pin("dbt/requirements-dbt.txt", "dbt-bigquery"),
    },
    "deployment_environment": os.environ["ENVIRONMENT"],
    # Schema contract: the newest migration this release requires, and the
    # oldest applied-schema state it can run against (rollback compatibility).
    "required_schema_version": manifest_lines[-1],
    "min_compatible_schema_version": manifest_lines[-1],
    "file_count": len(checksums),
    "file_checksums": checksums,
}
out = bundle_root / "release-manifest.json"
out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"release-manifest.json: {len(checksums)} files, schema {manifest['required_schema_version']}")
PY

# --- Deterministic archive ---------------------------------------------------------
ARCHIVE="${DIST_DIR}/atlas-bundle-${GIT_SHA}.tar.gz"
tar --sort=name --owner=0 --group=0 --numeric-owner \
  --mtime="UTC 2026-01-01" \
  -C "$STAGE_DIR" -cf - atlas-bundle | gzip -n >"$ARCHIVE"
CHECKSUM="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
echo "$CHECKSUM  $(basename "$ARCHIVE")" >"${ARCHIVE}.sha256"
cp "${BUNDLE_ROOT}/release-manifest.json" "${DIST_DIR}/release-manifest-${GIT_SHA}.json"

echo "bundle:   ${ARCHIVE}"
echo "checksum: ${CHECKSUM}"

# --- Create-only upload -------------------------------------------------------------
# Content identity is the per-file checksum map: a stored release for this SHA
# with identical file contents is reused (build metadata may differ across
# legitimate retries); different file contents for the same SHA is a hard fail.
if [[ "$UPLOAD" -eq 1 ]]; then
  RELEASE_URI="gs://${DEPLOYMENT_BUCKET}/atlas/releases/${GIT_SHA}"
  if gcloud storage ls "${RELEASE_URI}/release-manifest.json" >/dev/null 2>&1; then
    gcloud storage cat "${RELEASE_URI}/release-manifest.json" >"${STAGE_DIR}/existing-manifest.json"
    if "$PY" - "$BUNDLE_ROOT/release-manifest.json" "${STAGE_DIR}/existing-manifest.json" <<'PY'
import json
import sys

ours = json.load(open(sys.argv[1]))["file_checksums"]
theirs = json.load(open(sys.argv[2]))["file_checksums"]
ours.pop("release-manifest.json", None)
theirs.pop("release-manifest.json", None)
sys.exit(0 if ours == theirs else 1)
PY
    then
      echo "release ${GIT_SHA:0:12} already stored with identical content — reusing."
      echo "uri: ${RELEASE_URI}/atlas-bundle.tar.gz"
      exit 0
    fi
    echo "FATAL: ${RELEASE_URI} exists with DIFFERENT file contents for the same git SHA." >&2
    echo "Immutable releases are never overwritten. Investigate before retrying." >&2
    exit 1
  fi
  gcloud storage cp "$ARCHIVE" "${RELEASE_URI}/atlas-bundle.tar.gz"
  gcloud storage cp "${ARCHIVE}.sha256" "${RELEASE_URI}/atlas-bundle.tar.gz.sha256"
  gcloud storage cp "${BUNDLE_ROOT}/release-manifest.json" "${RELEASE_URI}/release-manifest.json"
  echo "uploaded: ${RELEASE_URI}/atlas-bundle.tar.gz"
fi
