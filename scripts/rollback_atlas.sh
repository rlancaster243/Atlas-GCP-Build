#!/usr/bin/env bash
# Runtime rollback to a prior validated immutable release (Sprint 4, Phase 14).
#
# Usage:
#   rollback_atlas.sh [--target-sha <sha>]
#
# Selects the newest SUCCESS deployment (excluding the currently deployed SHA)
# from atlas_ops.deployments unless --target-sha is given, verifies manifest,
# checksums, and schema compatibility, then re-promotes that release and runs a
# rollback smoke batch. Records ROLLED_BACK / ROLLBACK_FAILED.
#
# Never: deletes historical bundles, rewrites Git history, moves release tags,
# or reverses BigQuery migrations. Requires ATLAS_APPROVE_ROLLBACK_TEST=true
# for live execution (plus ATLAS_APPROVE_DEPLOY=true for the promotion itself).
set -uo pipefail

ATLAS_SCRIPTS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_atlas_deploy.sh
source "${ATLAS_SCRIPTS_ROOT}/lib_atlas_deploy.sh"
export PYTHONPATH="${ATLAS_SCRIPTS_ROOT}/../src:${PYTHONPATH:-}"

TARGET_SHA=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target-sha) TARGET_SHA="${2:?}"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ "${ATLAS_APPROVE_ROLLBACK_TEST:-false}" != "true" ]]; then
  echo "ATLAS_APPROVE_ROLLBACK_TEST != true — refusing to execute a live rollback." >&2
  exit 3
fi

# --- 1. Identify the currently deployed SHA -----------------------------------------
BUCKET="$(composer_bucket)"
CURRENT_SHA="$(gcloud storage cat "${BUCKET}/data/current/release-manifest.json" 2>/dev/null \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["git_sha"])' || echo "")"
if [[ -z "$CURRENT_SHA" ]]; then
  echo "Unable to determine currently deployed SHA from Composer runtime path." >&2
  exit 1
fi
echo "currently deployed: ${CURRENT_SHA}"

# --- 2. Identify the prior validated release ------------------------------------------
if [[ -z "$TARGET_SHA" ]]; then
  TARGET_SHA="$(ATLAS_CURRENT_SHA="$CURRENT_SHA" python3 - <<'PY'
import os

from atlas.ops.deployments import latest_successful_deployment

row = latest_successful_deployment("atlas-dev", exclude_git_sha=os.environ["ATLAS_CURRENT_SHA"])
print(row["git_sha"] if row else "")
PY
)"
fi
if [[ -z "$TARGET_SHA" ]]; then
  echo "No prior validated SUCCESS deployment found in atlas_ops.deployments." >&2
  exit 1
fi
if [[ "$TARGET_SHA" == "$CURRENT_SHA" ]]; then
  echo "Target SHA equals currently deployed SHA — nothing to roll back to." >&2
  exit 1
fi
echo "rollback target:    ${TARGET_SHA}"

# --- 3-11. Delegate to the deployment engine as a rollback -------------------------------
exec bash "${ATLAS_SCRIPTS_ROOT}/deploy_atlas_release.sh" \
  --git-sha "$TARGET_SHA" \
  --deployment-type rollback \
  --previous-git-sha "$CURRENT_SHA" \
  --skip-migrations
