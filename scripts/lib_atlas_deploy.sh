#!/usr/bin/env bash
# Shared functions for Atlas Composer deployment and rollback (Sprint 4).
# Sourced by deploy_atlas_release.sh, rollback_atlas.sh, and
# validate_atlas_deployment.sh — not executable on its own.

ATLAS_PROJECT_ID="${ATLAS_GCP_PROJECT_ID:-example-gcp-project}"
ATLAS_REGION="${ATLAS_COMPOSER_REGION:-us-central1}"
ATLAS_COMPOSER_ENV="${ATLAS_COMPOSER_ENV:-atlas-dev}"
ATLAS_DEPLOY_BUCKET="${ATLAS_DEPLOYMENT_BUCKET:-atlas-deployments-${ATLAS_PROJECT_ID}}"

# Run an Airflow CLI command inside the Composer environment.
# gcloud mixes kubectl noise into the stream; callers parse defensively.
composer_airflow() { # subcommand args...
  local sub="$1"
  shift
  gcloud composer environments run "$ATLAS_COMPOSER_ENV" \
    --project="$ATLAS_PROJECT_ID" --location="$ATLAS_REGION" \
    "$sub" -- "$@" 2>&1
}

composer_bucket() {
  local dag_prefix
  dag_prefix="$(gcloud composer environments describe "$ATLAS_COMPOSER_ENV" \
    --project="$ATLAS_PROJECT_ID" --location="$ATLAS_REGION" \
    --format='value(config.dagGcsPrefix)')"
  # dagGcsPrefix looks like gs://<bucket>/dags
  echo "${dag_prefix%/dags}"
}

# Download a stored immutable release and verify archive + per-file checksums.
# Sets FETCHED_BUNDLE_DIR to the extracted atlas-bundle directory.
fetch_and_verify_release() { # git_sha work_dir
  local git_sha="$1" work_dir="$2"
  local release_uri="gs://${ATLAS_DEPLOY_BUCKET}/atlas/releases/${git_sha}"
  echo "Fetching release ${release_uri}" >&2
  gcloud storage cp "${release_uri}/atlas-bundle.tar.gz" "${work_dir}/atlas-bundle.tar.gz" >&2
  gcloud storage cp "${release_uri}/atlas-bundle.tar.gz.sha256" "${work_dir}/atlas-bundle.tar.gz.sha256" >&2
  # Compare digests directly: the stored .sha256 records the builder's local
  # filename, which differs from the canonical stored object name.
  local expected actual
  expected="$(awk '{print $1}' "${work_dir}/atlas-bundle.tar.gz.sha256")"
  actual="$(sha256sum "${work_dir}/atlas-bundle.tar.gz" | awk '{print $1}')"
  if [[ -z "$expected" || "$expected" != "$actual" ]]; then
    echo "FATAL: archive checksum mismatch for release ${git_sha}" >&2
    echo "  expected ${expected:-<none>}" >&2
    echo "  actual   ${actual}" >&2
    return 1
  fi
  echo "archive checksum verified: ${actual}" >&2
  tar -xzf "${work_dir}/atlas-bundle.tar.gz" -C "$work_dir"
  local bundle_dir="${work_dir}/atlas-bundle"
  python3 - "$bundle_dir" <<'PY' >&2 || return 1
import hashlib
import json
import sys
from pathlib import Path

bundle = Path(sys.argv[1])
manifest = json.loads((bundle / "release-manifest.json").read_text(encoding="utf-8"))
bad = []
for rel, expected in manifest["file_checksums"].items():
    if rel == "release-manifest.json":
        continue
    actual = hashlib.sha256((bundle / rel).read_bytes()).hexdigest()
    if actual != expected:
        bad.append(rel)
if bad:
    print(f"FATAL: {len(bad)} file checksum mismatches: {bad[:5]}")
    raise SystemExit(1)
print(f"verified {len(manifest['file_checksums'])} file checksums for {manifest['git_sha'][:12]}")
PY
  # Consumed by sourcing scripts.
  # shellcheck disable=SC2034
  FETCHED_BUNDLE_DIR="$bundle_dir"
}

manifest_field() { # bundle_dir field
  python3 - "$1" "$2" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads((Path(sys.argv[1]) / "release-manifest.json").read_text(encoding="utf-8"))
value = manifest.get(sys.argv[2])
print("" if value is None else value)
PY
}

# Schema compatibility rule (ADR-010/ADR-015): a release may be promoted only
# when every migration up to its required_schema_version is APPLIED. For
# rollbacks the reverse direction is also checked: applied migrations the
# target release predates must all be additive — a `breaking`-flagged
# migration in the repository manifest blocks the rollback with
# forward-recovery guidance (S6-RBK-003).
check_schema_compatibility() { # bundle_dir [deployment_type]
  local bundle_dir="$1" deployment_type="${2:-deploy}"
  PYTHONPATH="${ATLAS_SCRIPTS_ROOT}/../src:${PYTHONPATH:-}" \
  python3 - "$bundle_dir" "$deployment_type" "${ATLAS_SCRIPTS_ROOT}/../sql/migrations/manifest.txt" <<'PY'
import json
import sys
from pathlib import Path

from atlas.ops.migrations import load_manifest, migration_status
from atlas.ops.rollback_compatibility import evaluate_rollback_compatibility

bundle = Path(sys.argv[1])
deployment_type = sys.argv[2]
repo_manifest_path = Path(sys.argv[3])
manifest = json.loads((bundle / "release-manifest.json").read_text(encoding="utf-8"))
required = manifest["required_schema_version"]

ledger = migration_status()
applied = [row["migration_id"] for row in ledger if row["status"] == "APPLIED"]
release_manifest_ids = [
    line.split("|")[0].strip()
    for line in (bundle / "sql/migrations/manifest.txt").read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.startswith("#")
]
missing = [m for m in release_manifest_ids if m not in applied]
if missing:
    print(f"schema check: {len(missing)} migrations pending for this release: {missing}")
    print("PENDING_MIGRATIONS")
    raise SystemExit(0)

if deployment_type == "rollback":
    decision = evaluate_rollback_compatibility(
        applied_migration_ids=applied,
        target_release_migration_ids=release_manifest_ids,
        manifest=load_manifest(repo_manifest_path),
    )
    print(f"schema check (rollback): {decision.reason}")
    if not decision.eligible:
        print("ROLLBACK_INCOMPATIBLE")
        raise SystemExit(0)

print(f"schema check: required {required} — all release migrations applied")
print("COMPATIBLE")
PY
}

promote_release_to_composer() { # bundle_dir deployment_id git_sha
  local bundle_dir="$1" deployment_id="$2" git_sha="$3"
  local bucket
  bucket="$(composer_bucket)"
  echo "Promoting to ${bucket} (dags/project_atlas + data/current)" >&2

  printf '{"deployment_id": "%s", "git_sha": "%s"}\n' "$deployment_id" "$git_sha" \
    >"${bundle_dir}/deployment-info.json"

  # --checksums-only is required: the deterministic bundle tar pins every
  # file mtime to a fixed date, so rsync's default size+mtime comparison
  # silently skips changed files whose size is unchanged (this left a stale
  # release-manifest.json behind on deployment atlas-dev-20260719T004112Z).
  # Runtime assets first so a parsed DAG never points at missing runtime files.
  gcloud storage rsync --recursive --checksums-only --delete-unmatched-destination-objects \
    --exclude='^dags/.*' \
    "$bundle_dir" "${bucket}/data/current" >&2
  # DAG parse-time assets last.
  gcloud storage rsync --recursive --checksums-only --delete-unmatched-destination-objects \
    "${bundle_dir}/dags" "${bucket}/dags/project_atlas" >&2
}

# Wait until the deployed DAG parses in Composer with no import errors.
wait_for_dag_parse() { # timeout_seconds
  local timeout="${1:-600}"
  local deadline=$((SECONDS + timeout))
  local out="" errors=""
  while (( SECONDS < deadline )); do
    out="$(composer_airflow dags list -o plain || true)"
    if echo "$out" | awk '{print $1}' | grep -qx "atlas_batch_pipeline"; then
      errors="$(composer_airflow dags list-import-errors -o plain || true)"
      if ! echo "$errors" | grep -q "project_atlas"; then
        echo "atlas_batch_pipeline parsed with no import errors" >&2
        return 0
      fi
      # Import errors can be stale: Airflow keeps the previous deployment's
      # error rows until the DAG processor re-evaluates (or stops seeing)
      # each file after the GCS sync. Keep polling until the deadline and
      # only fail if errors persist.
      echo "DAG import errors present (may be stale, retrying):" >&2
      echo "$errors" >&2
    fi
    sleep 20
  done
  echo "Timed out after ${timeout}s waiting for atlas_batch_pipeline to parse cleanly" >&2
  echo "Last dags list output:" >&2
  echo "$out" >&2
  if [[ -n "$errors" ]]; then
    echo "Last import errors:" >&2
    echo "$errors" >&2
  fi
  return 1
}

# Trigger a smoke run with an explicit run id and poll to terminal state.
# Echoes nothing; returns 0 on success. Callers know the dag_run_id they passed.
run_smoke_batch() { # dag_run_id conf_json timeout_seconds
  local dag_run_id="$1" conf_json="$2" timeout="${3:-2400}"
  composer_airflow dags unpause atlas_batch_pipeline >/dev/null 2>&1 || true
  echo "Triggering smoke run ${dag_run_id}" >&2
  composer_airflow dags trigger atlas_batch_pipeline --run-id "$dag_run_id" --conf "$conf_json" >&2 || {
    echo "Trigger failed" >&2
    return 1
  }
  local deadline=$((SECONDS + timeout))
  local state=""
  while (( SECONDS < deadline )); do
    # Airflow 3 prints "state, {conf...}" for runs triggered with --conf, so
    # match the leading token rather than anchoring the whole line.
    state="$(composer_airflow dags state atlas_batch_pipeline "$dag_run_id" \
      | grep -Eo '^(success|failed|running|queued)\b' | tail -1 || true)"
    echo "smoke run ${dag_run_id}: state=${state:-unknown} (${SECONDS}s elapsed)" >&2
    case "$state" in
      success)
        echo "Smoke run ${dag_run_id}: success" >&2
        return 0
        ;;
      failed)
        echo "Smoke run ${dag_run_id}: FAILED" >&2
        composer_airflow tasks states-for-dag-run atlas_batch_pipeline "$dag_run_id" >&2 || true
        return 1
        ;;
    esac
    sleep 30
  done
  echo "Smoke run ${dag_run_id}: timed out after ${timeout}s (last state: ${state:-unknown})" >&2
  return 1
}

bq_scalar() { # sql
  bq --project_id="$ATLAS_PROJECT_ID" query --use_legacy_sql=false --format=csv "$1" | tail -1
}
