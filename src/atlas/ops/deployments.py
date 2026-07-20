"""Durable deployment and rollback audit records (Sprint 4, Phase 10).

Grain: one row per deployment or rollback attempt in
``atlas_ops.deployments``, keyed by ``deployment_id`` and written with
idempotent parameterized MERGE statements. Deployments are a separate grain
from ``atlas_ops.pipeline_runs``: a deployment may reference the smoke
pipeline run it triggered, but never duplicates its row.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from google.cloud import bigquery

from atlas.config.settings import AtlasSettings, load_settings
from atlas.observability.cost import labeled_bigquery_client
from atlas.ops.audit import sanitize_error_message

ALLOWED_DEPLOYMENT_STATUSES = frozenset(
    {"RUNNING", "SUCCESS", "FAILED", "ROLLING_BACK", "ROLLED_BACK", "ROLLBACK_FAILED"}
)
ALLOWED_DEPLOYMENT_TYPES = frozenset({"deploy", "rollback"})


@dataclass(frozen=True)
class DeploymentRecord:
    """One durable audit row for a deployment or rollback attempt."""

    deployment_id: str
    git_sha: str
    environment: str
    deployment_type: str
    started_at: str
    status: str
    git_ref: str | None = None
    release_tag: str | None = None
    workflow_run_id: str | None = None
    actor: str | None = None
    completed_at: str | None = None
    artifact_uri: str | None = None
    artifact_checksum: str | None = None
    composer_environment: str | None = None
    composer_region: str | None = None
    smoke_pipeline_run_id: str | None = None
    previous_git_sha: str | None = None
    migration_count: int | None = None
    failure_stage: str | None = None
    error_type: str | None = None
    error_summary: str | None = None


def _table_fqn(settings: AtlasSettings) -> str:
    return f"{settings.gcp.project_id}.atlas_ops.deployments"


_INT64_FIELDS = frozenset({"migration_count"})


def _param_type(name: str, value: Any) -> str:
    if isinstance(value, bool):
        return "BOOL"
    if isinstance(value, int) or name in _INT64_FIELDS:
        return "INT64"
    return "STRING"


def upsert_deployment(
    record: DeploymentRecord,
    settings: AtlasSettings | None = None,
    *,
    client: bigquery.Client | None = None,
) -> None:
    """Merge one deployment audit row keyed by deployment_id."""
    if record.status not in ALLOWED_DEPLOYMENT_STATUSES:
        raise ValueError(f"Unsupported deployment status: {record.status}")
    if record.deployment_type not in ALLOWED_DEPLOYMENT_TYPES:
        raise ValueError(f"Unsupported deployment type: {record.deployment_type}")
    settings = settings or load_settings()
    bq_client = client or labeled_bigquery_client(settings.gcp.project_id, "deployment")
    query = f"""
        MERGE `{_table_fqn(settings)}` AS target
        USING (
          SELECT
            @deployment_id AS deployment_id,
            @git_sha AS git_sha,
            @git_ref AS git_ref,
            @release_tag AS release_tag,
            @environment AS environment,
            @workflow_run_id AS workflow_run_id,
            @actor AS actor,
            @deployment_type AS deployment_type,
            TIMESTAMP(@started_at) AS started_at,
            TIMESTAMP(@completed_at) AS completed_at,
            @status AS status,
            @artifact_uri AS artifact_uri,
            @artifact_checksum AS artifact_checksum,
            @composer_environment AS composer_environment,
            @composer_region AS composer_region,
            @smoke_pipeline_run_id AS smoke_pipeline_run_id,
            @previous_git_sha AS previous_git_sha,
            @migration_count AS migration_count,
            @failure_stage AS failure_stage,
            @error_type AS error_type,
            @error_summary AS error_summary
        ) AS source
        ON target.deployment_id = source.deployment_id
        WHEN MATCHED THEN UPDATE SET
          git_sha = source.git_sha,
          git_ref = source.git_ref,
          release_tag = source.release_tag,
          environment = source.environment,
          workflow_run_id = source.workflow_run_id,
          actor = source.actor,
          deployment_type = source.deployment_type,
          completed_at = source.completed_at,
          status = source.status,
          artifact_uri = source.artifact_uri,
          artifact_checksum = source.artifact_checksum,
          composer_environment = source.composer_environment,
          composer_region = source.composer_region,
          smoke_pipeline_run_id = source.smoke_pipeline_run_id,
          previous_git_sha = source.previous_git_sha,
          migration_count = source.migration_count,
          failure_stage = source.failure_stage,
          error_type = source.error_type,
          error_summary = source.error_summary,
          updated_at = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN INSERT (
          deployment_id, git_sha, git_ref, release_tag, environment,
          workflow_run_id, actor, deployment_type, started_at, completed_at,
          status, artifact_uri, artifact_checksum, composer_environment,
          composer_region, smoke_pipeline_run_id, previous_git_sha,
          migration_count, failure_stage, error_type, error_summary,
          created_at, updated_at
        ) VALUES (
          source.deployment_id, source.git_sha, source.git_ref, source.release_tag,
          source.environment, source.workflow_run_id, source.actor,
          source.deployment_type, source.started_at, source.completed_at,
          source.status, source.artifact_uri, source.artifact_checksum,
          source.composer_environment, source.composer_region,
          source.smoke_pipeline_run_id, source.previous_git_sha,
          source.migration_count, source.failure_stage, source.error_type,
          source.error_summary, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()
        )
    """
    params = asdict(record)
    params["error_summary"] = sanitize_error_message(record.error_summary)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter(name, _param_type(name, value), value)
            for name, value in params.items()
        ]
    )
    bq_client.query(query, job_config=job_config).result()


def start_deployment(
    *,
    deployment_id: str,
    git_sha: str,
    environment: str,
    deployment_type: str = "deploy",
    git_ref: str | None = None,
    release_tag: str | None = None,
    workflow_run_id: str | None = None,
    actor: str | None = None,
    artifact_uri: str | None = None,
    artifact_checksum: str | None = None,
    previous_git_sha: str | None = None,
    settings: AtlasSettings | None = None,
    client: bigquery.Client | None = None,
) -> DeploymentRecord:
    """Create or refresh a RUNNING (or ROLLING_BACK) deployment row."""
    status = "ROLLING_BACK" if deployment_type == "rollback" else "RUNNING"
    record = DeploymentRecord(
        deployment_id=deployment_id,
        git_sha=git_sha,
        environment=environment,
        deployment_type=deployment_type,
        started_at=datetime.now(tz=UTC).isoformat(),
        status=status,
        git_ref=git_ref,
        release_tag=release_tag,
        workflow_run_id=workflow_run_id,
        actor=actor,
        artifact_uri=artifact_uri,
        artifact_checksum=artifact_checksum,
        previous_git_sha=previous_git_sha,
    )
    upsert_deployment(record, settings=settings, client=client)
    return record


def finalize_deployment(
    record: DeploymentRecord,
    *,
    status: str,
    failure_stage: str | None = None,
    error_type: str | None = None,
    error_summary: str | None = None,
    smoke_pipeline_run_id: str | None = None,
    composer_environment: str | None = None,
    composer_region: str | None = None,
    migration_count: int | None = None,
    settings: AtlasSettings | None = None,
    client: bigquery.Client | None = None,
) -> DeploymentRecord:
    """Upsert the terminal state for one deployment attempt. Idempotent."""
    final = DeploymentRecord(
        **{
            **asdict(record),
            "completed_at": record.completed_at or datetime.now(tz=UTC).isoformat(),
            "status": status,
            "failure_stage": failure_stage,
            "error_type": error_type,
            "error_summary": error_summary,
            "smoke_pipeline_run_id": smoke_pipeline_run_id or record.smoke_pipeline_run_id,
            "composer_environment": composer_environment or record.composer_environment,
            "composer_region": composer_region or record.composer_region,
            "migration_count": migration_count if migration_count is not None else record.migration_count,
        }
    )
    upsert_deployment(final, settings=settings, client=client)
    return final


def query_deployment(
    deployment_id: str,
    settings: AtlasSettings | None = None,
    *,
    client: bigquery.Client | None = None,
) -> dict[str, Any] | None:
    """Fetch one deployment audit row as a dictionary."""
    settings = settings or load_settings()
    bq_client = client or labeled_bigquery_client(settings.gcp.project_id, "deployment")
    query = f"""
        SELECT * FROM `{_table_fqn(settings)}`
        WHERE deployment_id = @deployment_id
        LIMIT 1
    """
    rows = list(
        bq_client.query(
            query,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter("deployment_id", "STRING", deployment_id)]
            ),
        ).result()
    )
    if not rows:
        return None
    row = dict(rows[0].items())
    for key, value in row.items():
        if hasattr(value, "isoformat"):
            row[key] = value.isoformat()
    return row


def latest_successful_deployment(
    environment: str,
    settings: AtlasSettings | None = None,
    *,
    client: bigquery.Client | None = None,
    exclude_git_sha: str | None = None,
) -> dict[str, Any] | None:
    """Return the most recent SUCCESS (or ROLLED_BACK target) deployment row.

    Used by rollback to select the restore target: the newest deployment whose
    artifacts were fully validated, optionally excluding the currently broken SHA.
    """
    settings = settings or load_settings()
    bq_client = client or labeled_bigquery_client(settings.gcp.project_id, "deployment")
    query = f"""
        SELECT * FROM `{_table_fqn(settings)}`
        WHERE environment = @environment
          AND status = 'SUCCESS'
          AND (@exclude_git_sha IS NULL OR git_sha != @exclude_git_sha)
        ORDER BY completed_at DESC
        LIMIT 1
    """
    rows = list(
        bq_client.query(
            query,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("environment", "STRING", environment),
                    bigquery.ScalarQueryParameter("exclude_git_sha", "STRING", exclude_git_sha),
                ]
            ),
        ).result()
    )
    if not rows:
        return None
    row = dict(rows[0].items())
    for key, value in row.items():
        if hasattr(value, "isoformat"):
            row[key] = value.isoformat()
    return row
