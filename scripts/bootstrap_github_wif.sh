#!/usr/bin/env bash
# Bootstrap keyless GitHub-to-GCP authentication for Project Atlas (Sprint 4).
#
#   GitHub OIDC → Workload Identity Federation → service-account impersonation
#
# Behavior:
#   - idempotent: safe to re-run; existing resources are reused
#   - prints a full plan first; mutations require ATLAS_APPROVE_IAM=true
#   - never creates a service-account key
#   - validates the provider configuration after setup
#
# See docs/adr/ADR-009-workload-identity-federation.md.
set -euo pipefail

: "${ATLAS_GCP_PROJECT_ID:?Set ATLAS_GCP_PROJECT_ID}"
: "${ATLAS_GCP_PROJECT_NUMBER:?Set ATLAS_GCP_PROJECT_NUMBER}"
: "${ATLAS_GITHUB_REPOSITORY:?Set ATLAS_GITHUB_REPOSITORY as owner/repo}"

PROJECT_ID="${ATLAS_GCP_PROJECT_ID:-example-gcp-project}"
GITHUB_OWNER="${ATLAS_GITHUB_OWNER:-YOUR_GITHUB_OWNER}"
GITHUB_REPO="${ATLAS_GITHUB_REPOSITORY:-YOUR_GITHUB_OWNER/YOUR_REPOSITORY}"
POOL_ID="${ATLAS_WIF_POOL_ID:-atlas-github-pool}"
PROVIDER_ID="${ATLAS_WIF_PROVIDER_ID:-atlas-github-provider}"
INTEGRATION_SA="${ATLAS_INTEGRATION_SA_NAME:-atlas-github-integration}"
DEPLOYER_SA="${ATLAS_DEPLOYER_SA_NAME:-atlas-github-deployer}"
DEPLOYMENT_BUCKET="${ATLAS_DEPLOYMENT_BUCKET:-atlas-deployments-${PROJECT_ID}}"
# Dedicated CI bucket: integration tests never touch the canonical Sprint 1
# events bucket (which predates uniform bucket-level access, so it cannot
# carry IAM prefix conditions). Objects expire automatically after 7 days.
CI_BUCKET="${ATLAS_CI_BUCKET:-atlas-ci-${PROJECT_ID}}"
APPROVE="${ATLAS_APPROVE_IAM:-false}"

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
POOL_NAME="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}"
PROVIDER_NAME="${POOL_NAME}/providers/${PROVIDER_ID}"
INTEGRATION_EMAIL="${INTEGRATION_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
DEPLOYER_EMAIL="${DEPLOYER_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
REPO_FULL="${GITHUB_OWNER}/${GITHUB_REPO}"

# Trust boundary: only workflows from this exact repository may authenticate,
# and only runs on refs/heads/main may impersonate either service account.
# assertion.repository_owner guards against repository renames/transfers.
ATTRIBUTE_CONDITION="assertion.repository_owner == '${GITHUB_OWNER}' && assertion.repository == '${REPO_FULL}'"
MAIN_REF_MEMBER="principalSet://iam.googleapis.com/${POOL_NAME}/attribute.repository_and_ref/${REPO_FULL}@refs/heads/main"

cat <<PLAN
================= WIF bootstrap plan =================
Project:            ${PROJECT_ID} (${PROJECT_NUMBER})
Pool:               ${POOL_ID}
Provider:           ${PROVIDER_ID}
  issuer:           https://token.actions.githubusercontent.com
  condition:        ${ATTRIBUTE_CONDITION}
  mapped claims:    sub, repository, repository_owner, ref,
                    repository_and_ref (repository@ref, used for bindings)
Service accounts:
  ${INTEGRATION_EMAIL}
    roles/bigquery.jobUser                   (project)
    roles/bigquery.dataEditor                (project; needed to create
                                              temporary atlas_ci_* datasets —
                                              documented risk in ADR-009)
    roles/storage.admin                      (dedicated CI bucket only,
                                              gs://${CI_BUCKET}, 7-day TTL)
  ${DEPLOYER_EMAIL}
    roles/bigquery.jobUser                   (project)
    roles/bigquery.dataEditor                (project; additive migrations +
                                              atlas_ops audit writes)
    roles/storage.admin                      (deployment bucket only)
    roles/composer.user                      (project)
    roles/composer.environmentAndStorageObjectAdmin (project; DAG/data sync)
    roles/iam.serviceAccountUser             (on the Composer runtime SA,
                                              granted at environment creation)
WIF bindings (roles/iam.workloadIdentityUser):
  both SAs ← ${MAIN_REF_MEMBER}
Deployment bucket:  gs://${DEPLOYMENT_BUCKET} (created if missing, uniform
                    access, versioning on)
CI bucket:          gs://${CI_BUCKET} (created if missing, uniform access,
                    objects auto-deleted after 7 days)
No service-account keys are created at any point.
=======================================================
PLAN

if [[ "$APPROVE" != "true" ]]; then
  echo "ATLAS_APPROVE_IAM != true — plan only, no changes made."
  exit 0
fi

run() {
  echo "+ $*"
  "$@"
}

# --- Pool ------------------------------------------------------------------
if gcloud iam workload-identity-pools describe "$POOL_ID" --location=global \
     --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "Pool ${POOL_ID} exists — reusing."
else
  run gcloud iam workload-identity-pools create "$POOL_ID" \
    --location=global --project="$PROJECT_ID" \
    --display-name="Atlas GitHub Actions pool"
fi

# --- Provider ---------------------------------------------------------------
if gcloud iam workload-identity-pools providers describe "$PROVIDER_ID" \
     --workload-identity-pool="$POOL_ID" --location=global \
     --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "Provider ${PROVIDER_ID} exists — updating condition and mapping."
  run gcloud iam workload-identity-pools providers update-oidc "$PROVIDER_ID" \
    --workload-identity-pool="$POOL_ID" --location=global --project="$PROJECT_ID" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner,attribute.ref=assertion.ref,attribute.repository_and_ref=assertion.repository+'@'+assertion.ref" \
    --attribute-condition="$ATTRIBUTE_CONDITION"
else
  run gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_ID" \
    --workload-identity-pool="$POOL_ID" --location=global --project="$PROJECT_ID" \
    --display-name="Atlas GitHub OIDC" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner,attribute.ref=assertion.ref,attribute.repository_and_ref=assertion.repository+'@'+assertion.ref" \
    --attribute-condition="$ATTRIBUTE_CONDITION"
fi

# --- Service accounts --------------------------------------------------------
for sa in "$INTEGRATION_SA" "$DEPLOYER_SA"; do
  email="${sa}@${PROJECT_ID}.iam.gserviceaccount.com"
  if gcloud iam service-accounts describe "$email" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo "Service account ${email} exists — reusing."
  else
    run gcloud iam service-accounts create "$sa" --project="$PROJECT_ID" \
      --display-name="Atlas GitHub ${sa#atlas-github-}"
  fi
done

# --- Deployment bucket -------------------------------------------------------
if gcloud storage buckets describe "gs://${DEPLOYMENT_BUCKET}" >/dev/null 2>&1; then
  echo "Bucket gs://${DEPLOYMENT_BUCKET} exists — reusing."
else
  run gcloud storage buckets create "gs://${DEPLOYMENT_BUCKET}" \
    --project="$PROJECT_ID" --location=US \
    --uniform-bucket-level-access
  run gcloud storage buckets update "gs://${DEPLOYMENT_BUCKET}" --versioning
fi

# --- Project-level roles ------------------------------------------------------
grant_project_role() {
  local member="$1" role="$2"
  run gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="$member" --role="$role" --condition=None --quiet >/dev/null
}

grant_project_role "serviceAccount:${INTEGRATION_EMAIL}" roles/bigquery.jobUser
grant_project_role "serviceAccount:${INTEGRATION_EMAIL}" roles/bigquery.dataEditor
grant_project_role "serviceAccount:${DEPLOYER_EMAIL}" roles/bigquery.jobUser
grant_project_role "serviceAccount:${DEPLOYER_EMAIL}" roles/bigquery.dataEditor
grant_project_role "serviceAccount:${DEPLOYER_EMAIL}" roles/composer.user
grant_project_role "serviceAccount:${DEPLOYER_EMAIL}" roles/composer.environmentAndStorageObjectAdmin

# --- CI bucket -----------------------------------------------------------------
if gcloud storage buckets describe "gs://${CI_BUCKET}" >/dev/null 2>&1; then
  echo "Bucket gs://${CI_BUCKET} exists — reusing."
else
  run gcloud storage buckets create "gs://${CI_BUCKET}" \
    --project="$PROJECT_ID" --location=US \
    --uniform-bucket-level-access
  LIFECYCLE_TMP="$(mktemp)"
  cat >"$LIFECYCLE_TMP" <<'JSON'
{"rule": [{"action": {"type": "Delete"}, "condition": {"age": 7}}]}
JSON
  run gcloud storage buckets update "gs://${CI_BUCKET}" --lifecycle-file="$LIFECYCLE_TMP"
  rm -f "$LIFECYCLE_TMP"
fi

# --- Bucket-scoped roles ------------------------------------------------------
# Integration: full control of the dedicated CI bucket only.
run gcloud storage buckets add-iam-policy-binding "gs://${CI_BUCKET}" \
  --member="serviceAccount:${INTEGRATION_EMAIL}" \
  --role="roles/storage.admin" >/dev/null
echo "+ integration storage.admin bound to gs://${CI_BUCKET}"

# Deployer: full control of the deployment bucket only.
run gcloud storage buckets add-iam-policy-binding "gs://${DEPLOYMENT_BUCKET}" \
  --member="serviceAccount:${DEPLOYER_EMAIL}" \
  --role="roles/storage.admin" >/dev/null
echo "+ deployer storage.admin bound to gs://${DEPLOYMENT_BUCKET}"

# --- WIF impersonation bindings ----------------------------------------------
for email in "$INTEGRATION_EMAIL" "$DEPLOYER_EMAIL"; do
  run gcloud iam service-accounts add-iam-policy-binding "$email" \
    --project="$PROJECT_ID" \
    --member="$MAIN_REF_MEMBER" \
    --role="roles/iam.workloadIdentityUser" >/dev/null
  echo "+ ${email} impersonable by ${REPO_FULL}@refs/heads/main"
done

# --- Post-setup validation -----------------------------------------------------
echo ""
echo "=== Validation ==="
gcloud iam workload-identity-pools providers describe "$PROVIDER_ID" \
  --workload-identity-pool="$POOL_ID" --location=global --project="$PROJECT_ID" \
  --format="yaml(name,state,attributeCondition,oidc.issuerUri)"
for email in "$INTEGRATION_EMAIL" "$DEPLOYER_EMAIL"; do
  echo "--- ${email} impersonation bindings:"
  gcloud iam service-accounts get-iam-policy "$email" --project="$PROJECT_ID" \
    --format="table(bindings.role,bindings.members)" 2>/dev/null | sed 's/^/    /'
done

cat <<DONE

WIF bootstrap complete. GitHub workflow configuration values:
  workload_identity_provider: ${PROVIDER_NAME}
  integration service_account: ${INTEGRATION_EMAIL}
  deployer service_account:    ${DEPLOYER_EMAIL}
These are resource identifiers, not secrets; commit them in workflow files.
A full end-to-end token exchange can only be validated from a real GitHub
Actions run (see the atlas-integration workflow).
DONE
