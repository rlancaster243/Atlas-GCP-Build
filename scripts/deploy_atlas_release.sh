#!/usr/bin/env bash
# Controlled Atlas deployment to managed Composer (Sprint 4, Phase 11).
#
# Usage:
#   deploy_atlas_release.sh --git-sha <sha> [--deployment-id <id>]
#       [--deployment-type deploy|rollback] [--previous-git-sha <sha>]
#       [--leave-paused] [--skip-migrations]
#
# Requires ATLAS_APPROVE_DEPLOY=true. Stages (audited in atlas_ops.deployments):
#   fetch_release → schema_check → migrations → promote → dag_parse →
#   smoke_batch → smoke_validation → finalize
# A failure at any stage records FAILED (or ROLLBACK_FAILED) with the stage
# name and leaves the immutable release evidence intact.
set -uo pipefail

ATLAS_SCRIPTS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_atlas_deploy.sh
source "${ATLAS_SCRIPTS_ROOT}/lib_atlas_deploy.sh"
export PYTHONPATH="${ATLAS_SCRIPTS_ROOT}/../src:${PYTHONPATH:-}"

GIT_SHA=""
DEPLOYMENT_ID=""
DEPLOYMENT_TYPE="deploy"
PREVIOUS_SHA=""
LEAVE_PAUSED=0
SKIP_MIGRATIONS=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --git-sha) GIT_SHA="${2:?}"; shift 2 ;;
    --deployment-id) DEPLOYMENT_ID="${2:?}"; shift 2 ;;
    --deployment-type) DEPLOYMENT_TYPE="${2:?}"; shift 2 ;;
    --previous-git-sha) PREVIOUS_SHA="${2:?}"; shift 2 ;;
    --leave-paused) LEAVE_PAUSED=1; shift ;;
    --skip-migrations) SKIP_MIGRATIONS=1; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$GIT_SHA" ]] || { echo "--git-sha is required" >&2; exit 2; }

if [[ "${ATLAS_APPROVE_DEPLOY:-false}" != "true" ]]; then
  echo "ATLAS_APPROVE_DEPLOY != true — refusing to deploy." >&2
  exit 3
fi

SHORT_SHA="${GIT_SHA:0:8}"
RUN_TOKEN="${GITHUB_RUN_ID:-local$(date -u +%s)}"
DEPLOYMENT_ID="${DEPLOYMENT_ID:-atlas-dev-$(date -u +%Y%m%dT%H%M%SZ)-${SHORT_SHA}}"
SMOKE_BATCH_ID="atlas-smoke-${SHORT_SHA}-${RUN_TOKEN}"
SMOKE_PIPELINE_RUN_ID="${SMOKE_BATCH_ID}-run"
SMOKE_DAG_RUN_ID="smoke__${DEPLOYMENT_ID}"
PROCESSING_DATE="$(date -u +%F)"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

echo "=== Atlas ${DEPLOYMENT_TYPE}: ${GIT_SHA} → ${ATLAS_COMPOSER_ENV} (${ATLAS_REGION}) ==="
echo "deployment_id: ${DEPLOYMENT_ID}"
echo "smoke batch:   ${SMOKE_BATCH_ID}"

# --- Audit helpers ----------------------------------------------------------------
audit() { # status [failure_stage] [error_summary]
  ATLAS_AUDIT_STATUS="$1" ATLAS_AUDIT_STAGE="${2:-}" ATLAS_AUDIT_ERROR="${3:-}" \
  ATLAS_DEPLOYMENT_ID="$DEPLOYMENT_ID" ATLAS_GIT_SHA="$GIT_SHA" \
  ATLAS_DEPLOYMENT_TYPE="$DEPLOYMENT_TYPE" ATLAS_PREVIOUS_SHA="$PREVIOUS_SHA" \
  ATLAS_SMOKE_RUN_ID="$SMOKE_PIPELINE_RUN_ID" ATLAS_ARTIFACT_URI="${ARTIFACT_URI:-}" \
  ATLAS_ARTIFACT_CHECKSUM="${ARTIFACT_CHECKSUM:-}" ATLAS_MIGRATION_COUNT="${MIGRATION_COUNT:-}" \
  python3 - <<'PY'
import os

from atlas.ops.deployments import DeploymentRecord, upsert_deployment
from datetime import UTC, datetime

status = os.environ["ATLAS_AUDIT_STATUS"]
started = os.environ.get("ATLAS_DEPLOY_STARTED_AT") or datetime.now(tz=UTC).isoformat()
terminal = status in {"SUCCESS", "FAILED", "ROLLED_BACK", "ROLLBACK_FAILED"}
record = DeploymentRecord(
    deployment_id=os.environ["ATLAS_DEPLOYMENT_ID"],
    git_sha=os.environ["ATLAS_GIT_SHA"],
    environment="atlas-dev",
    deployment_type=os.environ["ATLAS_DEPLOYMENT_TYPE"],
    started_at=started,
    status=status,
    git_ref=os.environ.get("GITHUB_REF"),
    workflow_run_id=os.environ.get("GITHUB_RUN_ID"),
    actor=os.environ.get("GITHUB_ACTOR") or os.environ.get("USER"),
    completed_at=datetime.now(tz=UTC).isoformat() if terminal else None,
    artifact_uri=os.environ.get("ATLAS_ARTIFACT_URI") or None,
    artifact_checksum=os.environ.get("ATLAS_ARTIFACT_CHECKSUM") or None,
    composer_environment=os.environ.get("ATLAS_COMPOSER_ENV", "atlas-dev"),
    composer_region=os.environ.get("ATLAS_COMPOSER_REGION", "us-central1"),
    smoke_pipeline_run_id=os.environ["ATLAS_SMOKE_RUN_ID"] if terminal else None,
    previous_git_sha=os.environ.get("ATLAS_PREVIOUS_SHA") or None,
    migration_count=int(os.environ["ATLAS_MIGRATION_COUNT"]) if os.environ.get("ATLAS_MIGRATION_COUNT") else None,
    failure_stage=os.environ.get("ATLAS_AUDIT_STAGE") or None,
    error_type="DeploymentStageFailure" if os.environ.get("ATLAS_AUDIT_STAGE") else None,
    error_summary=os.environ.get("ATLAS_AUDIT_ERROR") or None,
)
upsert_deployment(record)
print(f"audit: {record.deployment_id} -> {status}"
      + (f" (stage {record.failure_stage})" if record.failure_stage else ""))
PY
}

FAIL_STATUS="FAILED"
[[ "$DEPLOYMENT_TYPE" == "rollback" ]] && FAIL_STATUS="ROLLBACK_FAILED"

fail_stage() { # stage message
  echo "STAGE FAILED: $1 — $2" >&2
  audit "$FAIL_STATUS" "$1" "$2" || echo "WARNING: failed to record audit row" >&2
  echo "Recovery: inspect logs above, then re-run this script with the same" >&2
  echo "  --git-sha ${GIT_SHA} (deployment records are idempotent per deployment_id)" >&2
  exit 1
}

export ATLAS_DEPLOY_STARTED_AT
ATLAS_DEPLOY_STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"

# --- Stage 1: fetch and verify immutable release ------------------------------------
ARTIFACT_URI="gs://${ATLAS_DEPLOY_BUCKET}/atlas/releases/${GIT_SHA}/atlas-bundle.tar.gz"
if ! fetch_and_verify_release "$GIT_SHA" "$WORK_DIR"; then
  audit "$( [[ "$DEPLOYMENT_TYPE" == "rollback" ]] && echo ROLLING_BACK || echo RUNNING )" || true
  fail_stage "fetch_release" "release bundle missing or checksum-invalid for ${GIT_SHA}"
fi
BUNDLE_DIR="$FETCHED_BUNDLE_DIR"
ARTIFACT_CHECKSUM="$(awk '{print $1}' "${WORK_DIR}/atlas-bundle.tar.gz.sha256")"
INITIAL_STATUS="RUNNING"
[[ "$DEPLOYMENT_TYPE" == "rollback" ]] && INITIAL_STATUS="ROLLING_BACK"
audit "$INITIAL_STATUS" || fail_stage "start_audit" "unable to write atlas_ops.deployments"

# --- Stage 2: schema compatibility ----------------------------------------------------
SCHEMA_RESULT="$(check_schema_compatibility "$BUNDLE_DIR" "$DEPLOYMENT_TYPE" | tee /dev/stderr | tail -1)" \
  || fail_stage "schema_check" "schema compatibility evaluation failed"
if [[ "$SCHEMA_RESULT" == "PENDING_MIGRATIONS" && "$DEPLOYMENT_TYPE" == "rollback" ]]; then
  fail_stage "schema_check" "rollback target requires unapplied migrations — incompatible"
fi
if [[ "$SCHEMA_RESULT" == "ROLLBACK_INCOMPATIBLE" ]]; then
  # S6-RBK-003: the applied schema crossed a breaking-migration boundary the
  # target release predates. Never reversed automatically — forward fix only.
  fail_stage "schema_check" "rollback blocked by breaking migration boundary — recover forward"
fi

# --- Stage 3: additive migrations (deploy only) ----------------------------------------
MIGRATION_COUNT=0
if [[ "$SKIP_MIGRATIONS" -eq 0 && "$DEPLOYMENT_TYPE" == "deploy" ]]; then
  MIGRATION_OUT="$(bash "${BUNDLE_DIR}/scripts/apply_atlas_migrations.sh" --mode apply)" \
    || fail_stage "migrations" "migration apply failed (ledger records the failing id)"
  echo "$MIGRATION_OUT"
  MIGRATION_COUNT="$(echo "$MIGRATION_OUT" | grep -c "APPLIED_NOW" || true)"
fi

# --- Stage 4: promote to Composer -------------------------------------------------------
promote_release_to_composer "$BUNDLE_DIR" "$DEPLOYMENT_ID" "$GIT_SHA" \
  || fail_stage "promote" "asset promotion to Composer bucket failed"

# --- Stage 5: DAG parse verification ------------------------------------------------------
wait_for_dag_parse 600 || fail_stage "dag_parse" "DAG failed to parse after promotion"

# --- Stage 6: smoke batch -------------------------------------------------------------------
SMOKE_CONF="$(printf '{"batch_id": "%s", "pipeline_run_id": "%s", "processing_date": "%s"}' \
  "$SMOKE_BATCH_ID" "$SMOKE_PIPELINE_RUN_ID" "$PROCESSING_DATE")"
run_smoke_batch "$SMOKE_DAG_RUN_ID" "$SMOKE_CONF" 2400 \
  || fail_stage "smoke_batch" "smoke run did not reach terminal SUCCESS"

# --- Stage 7: smoke validation ---------------------------------------------------------------
bash "${ATLAS_SCRIPTS_ROOT}/validate_atlas_deployment.sh" \
  --git-sha "$GIT_SHA" \
  --deployment-id "$DEPLOYMENT_ID" \
  --batch-id "$SMOKE_BATCH_ID" \
  --pipeline-run-id "$SMOKE_PIPELINE_RUN_ID" \
  --processing-date "$PROCESSING_DATE" \
  || fail_stage "smoke_validation" "post-deployment smoke validation failed"

# --- Stage 8: finalize ------------------------------------------------------------------------
if [[ "$LEAVE_PAUSED" -eq 1 ]]; then
  composer_airflow dags pause atlas_batch_pipeline >/dev/null 2>&1 || true
  echo "DAG left paused per request."
fi
FINAL_STATUS="SUCCESS"
[[ "$DEPLOYMENT_TYPE" == "rollback" ]] && FINAL_STATUS="ROLLED_BACK"
audit "$FINAL_STATUS" || fail_stage "finalize" "unable to finalize atlas_ops.deployments"

echo ""
echo "=== ${DEPLOYMENT_TYPE} ${FINAL_STATUS}: ${GIT_SHA} ==="
echo "deployment_id:      ${DEPLOYMENT_ID}"
echo "artifact:           ${ARTIFACT_URI}"
echo "artifact checksum:  ${ARTIFACT_CHECKSUM}"
echo "smoke run:          ${SMOKE_PIPELINE_RUN_ID}"
