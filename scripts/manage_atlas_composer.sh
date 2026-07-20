#!/usr/bin/env bash
# Ephemeral Atlas Composer environment lifecycle (Sprint 4, Phase 12 / ADR-010).
#
# Usage:
#   manage_atlas_composer.sh status
#   manage_atlas_composer.sh create   # requires ATLAS_APPROVE_COMPOSER_CREATE=true
#                                     # (and ATLAS_APPROVE_IAM=true for SA setup)
#   manage_atlas_composer.sh delete   # tears the environment down (ephemeral policy)
#
# Owner decision (ADR-010): Composer exists only for evidence capture and is
# deleted afterwards. Never leave it running unattended.
set -euo pipefail

PROJECT_ID="${ATLAS_GCP_PROJECT_ID:-example-gcp-project}"
REGION="${ATLAS_COMPOSER_REGION:-us-central1}"
ENV_NAME="${ATLAS_COMPOSER_ENV:-atlas-dev}"
# Verified against available images and local Airflow 3.1.7 parity (ADR-005,
# amended): build.12 is no longer offered; owner approved build.13.
IMAGE_VERSION="composer-3-airflow-3.1.7-build.13"
RUNTIME_SA="atlas-composer-runtime"
RUNTIME_EMAIL="${RUNTIME_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
EVENTS_BUCKET="${ATLAS_GCS_BUCKET:-atlas-raw-events-${PROJECT_ID}}"
DEPLOYMENT_BUCKET="${ATLAS_DEPLOYMENT_BUCKET:-atlas-deployments-${PROJECT_ID}}"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"

ACTION="${1:?Usage: $0 status|create|delete}"

case "$ACTION" in
  status)
    gcloud composer environments describe "$ENV_NAME" --location="$REGION" \
      --project="$PROJECT_ID" \
      --format="yaml(name,state,config.softwareConfig.imageVersion,config.dagGcsPrefix,config.nodeConfig.serviceAccount)" \
      2>/dev/null || echo "Environment ${ENV_NAME} does not exist in ${REGION}."
    ;;

  create)
    if [[ "${ATLAS_APPROVE_COMPOSER_CREATE:-false}" != "true" ]]; then
      echo "ATLAS_APPROVE_COMPOSER_CREATE != true — refusing to create Composer environment." >&2
      echo "Estimated cost while running: roughly USD 0.35-0.50/hour for a small" >&2
      echo "Composer 3 environment (~USD 300/month if left alive — ADR-010 forbids that)." >&2
      exit 3
    fi
    if gcloud composer environments describe "$ENV_NAME" --location="$REGION" \
         --project="$PROJECT_ID" >/dev/null 2>&1; then
      echo "Environment ${ENV_NAME} already exists — reusing."
      exit 0
    fi

    echo "Enabling composer.googleapis.com..."
    gcloud services enable composer.googleapis.com --project="$PROJECT_ID"

    if [[ "${ATLAS_APPROVE_IAM:-false}" == "true" ]]; then
      # Composer service agent needs the V2 extension role for Composer 3.
      gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:service-${PROJECT_NUMBER}@cloudcomposer-accounts.iam.gserviceaccount.com" \
        --role="roles/composer.ServiceAgentV2Ext" --condition=None --quiet >/dev/null

      if ! gcloud iam service-accounts describe "$RUNTIME_EMAIL" --project="$PROJECT_ID" >/dev/null 2>&1; then
        gcloud iam service-accounts create "$RUNTIME_SA" --project="$PROJECT_ID" \
          --display-name="Atlas Composer runtime"
      fi
      # Newly created service accounts propagate asynchronously; retry bindings.
      # resourceViewer: the observability monitor's cost check reads
      # region-us.INFORMATION_SCHEMA.JOBS, which needs bigquery.jobs.listAll
      # (found live in Sprint 5: cost_anomaly returned 403 without it).
      for role in roles/composer.worker roles/bigquery.jobUser roles/bigquery.dataEditor roles/bigquery.resourceViewer; do
        for attempt in 1 2 3 4 5; do
          if gcloud projects add-iam-policy-binding "$PROJECT_ID" \
               --member="serviceAccount:${RUNTIME_EMAIL}" --role="$role" \
               --condition=None --quiet >/dev/null 2>&1; then
            break
          fi
          if [[ "$attempt" -eq 5 ]]; then
            echo "FATAL: could not bind ${role} to ${RUNTIME_EMAIL}" >&2
            exit 1
          fi
          echo "  binding ${role} not ready (attempt ${attempt}); retrying in $((attempt * 5))s..."
          sleep $((attempt * 5))
        done
      done
      gcloud storage buckets add-iam-policy-binding "gs://${EVENTS_BUCKET}" \
        --member="serviceAccount:${RUNTIME_EMAIL}" --role="roles/storage.objectAdmin" >/dev/null
      gcloud storage buckets add-iam-policy-binding "gs://${DEPLOYMENT_BUCKET}" \
        --member="serviceAccount:${RUNTIME_EMAIL}" --role="roles/storage.objectViewer" >/dev/null
      # The deployer must be able to attach the runtime SA to the environment.
      gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_EMAIL" \
        --project="$PROJECT_ID" \
        --member="serviceAccount:atlas-github-deployer@${PROJECT_ID}.iam.gserviceaccount.com" \
        --role="roles/iam.serviceAccountUser" >/dev/null
      echo "Runtime service account ${RUNTIME_EMAIL} configured."
    else
      echo "ATLAS_APPROVE_IAM != true — assuming ${RUNTIME_EMAIL} and grants already exist."
    fi

    echo "Creating ${ENV_NAME} (${IMAGE_VERSION}, ${REGION}, size small). This takes ~25 minutes..."
    gcloud composer environments create "$ENV_NAME" \
      --project="$PROJECT_ID" \
      --location="$REGION" \
      --image-version="$IMAGE_VERSION" \
      --environment-size=small \
      --service-account="$RUNTIME_EMAIL" \
      --env-variables="ATLAS_ROOT=/home/airflow/gcs/data/current,ATLAS_GCP_PROJECT_ID=${PROJECT_ID},ATLAS_GCS_BUCKET=${EVENTS_BUCKET},ATLAS_BQ_DATASET=atlas_raw,ATLAS_DBT_DATASET=atlas,DBT_PROJECT_DIR=/home/airflow/gcs/data/current/dbt/atlas_dbt,DBT_PROFILES_DIR=/home/airflow/gcs/data/current/dbt/profiles,DBT_LOCATION=US,DBT_TARGET_PATH=/tmp/dbt-target,DBT_LOG_PATH=/tmp/dbt-logs,ATLAS_LOG_TO_CLOUD_LOGGING=true,ATLAS_ENVIRONMENT=atlas-dev"

    echo "Installing pinned dbt PyPI packages (second long-running operation)..."
    PKG_FILE="$(mktemp)"
    grep -E '^(dbt-core|dbt-bigquery)==' "$(dirname "${BASH_SOURCE[0]}")/../dbt/requirements-dbt.txt" >"$PKG_FILE"
    cat "$PKG_FILE"
    gcloud composer environments update "$ENV_NAME" \
      --project="$PROJECT_ID" --location="$REGION" \
      --update-pypi-packages-from-file="$PKG_FILE"
    rm -f "$PKG_FILE"

    gcloud composer environments describe "$ENV_NAME" --location="$REGION" \
      --project="$PROJECT_ID" \
      --format="yaml(state,config.softwareConfig.imageVersion,config.dagGcsPrefix)"
    echo "Composer environment ready. Remember: delete it after evidence capture (ADR-010)."
    ;;

  delete)
    if ! gcloud composer environments describe "$ENV_NAME" --location="$REGION" \
         --project="$PROJECT_ID" >/dev/null 2>&1; then
      echo "Environment ${ENV_NAME} does not exist — nothing to delete."
      exit 0
    fi
    echo "Deleting ${ENV_NAME} in ${REGION} (ephemeral policy, ADR-010)..."
    gcloud composer environments delete "$ENV_NAME" \
      --project="$PROJECT_ID" --location="$REGION" --quiet
    echo "Deleted. Note: the Composer-created bucket is retained by GCP; remove it"
    echo "manually if evidence has been captured elsewhere."
    ;;

  *)
    echo "Usage: $0 status|create|delete" >&2
    exit 2
    ;;
esac
