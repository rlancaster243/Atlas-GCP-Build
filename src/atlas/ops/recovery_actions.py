"""Recovery-action audit records (Sprint 6, Phase 4 / ADR-014).

Grain: one row per recovery action attempt in ``atlas_ops.recovery_actions``,
keyed by ``recovery_id`` and written with idempotent parameterized MERGE.
Recovery actions are a separate grain from pipeline runs and deployments:
they *link* to incidents, pipeline runs, batches, and deployments but never
mutate those records.

Verification contract: a recovery attempt may only be finalized as SUCCESS
when its verification passed (``verification_status="VERIFIED"``). Finalizing
SUCCESS without verification raises — an unverified "recovery" is not a
recovery (ADR-014).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import Any

from google.cloud import bigquery

from atlas.config.settings import AtlasSettings, load_settings
from atlas.observability.cost import labeled_bigquery_client
from atlas.observability.logging import emit_event
from atlas.ops.audit import sanitize_error_message

ALLOWED_ACTION_TYPES = frozenset(
    {
        "RETRY_TASK",
        "RERUN_BATCH",
        "REPAIR_PARTIAL_LOAD",
        "QUARANTINE_BATCH",
        "BACKFILL",
        "RESTORE_RELEASE",
        "FORWARD_MIGRATION",
        "RESTORE_IAM",
        "REBUILD_PARTITION",
        "PAUSE_SCHEDULE",
        "RESUME_SCHEDULE",
        "RECONSTRUCT_AUDIT",
        "RESET_MONITOR",
        "MANUAL_CONTAINMENT",
    }
)

ALLOWED_STATUSES = frozenset({"RUNNING", "SUCCESS", "FAILED", "PARTIAL", "ABORTED"})
ALLOWED_VERIFICATION_STATUSES = frozenset({"PENDING", "VERIFIED", "FAILED", "SKIPPED"})


@dataclass(frozen=True)
class RecoveryActionRecord:
    """One durable recovery-action audit row."""

    recovery_id: str
    action_type: str
    status: str
    incident_id: str | None = None
    scenario_id: str | None = None
    pipeline_run_id: str | None = None
    batch_id: str | None = None
    deployment_id: str | None = None
    operator: str | None = None
    environment: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    source_state: str | None = None
    target_state: str | None = None
    verification_status: str | None = None
    error_type: str | None = None
    error_summary: str | None = None
    git_sha: str | None = None


def _table_fqn(settings: AtlasSettings) -> str:
    return f"{settings.gcp.project_id}.atlas_ops.recovery_actions"


_TIMESTAMP_FIELDS = frozenset({"started_at", "completed_at"})
_KEY_FIELDS = ("recovery_id",)


def _validate(record: RecoveryActionRecord) -> None:
    if record.action_type not in ALLOWED_ACTION_TYPES:
        raise ValueError(f"Unsupported recovery action type: {record.action_type}")
    if record.status not in ALLOWED_STATUSES:
        raise ValueError(f"Unsupported recovery status: {record.status}")
    if (
        record.verification_status is not None
        and record.verification_status not in ALLOWED_VERIFICATION_STATUSES
    ):
        raise ValueError(f"Unsupported verification status: {record.verification_status}")
    if record.status == "SUCCESS" and record.verification_status != "VERIFIED":
        raise ValueError(
            "recovery status SUCCESS requires verification_status=VERIFIED (ADR-014: "
            "no recovery is successful before verification passes)"
        )


def upsert_recovery_action(
    record: RecoveryActionRecord,
    settings: AtlasSettings | None = None,
    *,
    client: bigquery.Client | None = None,
) -> None:
    """Merge one recovery-action row keyed by recovery_id."""
    _validate(record)
    settings = settings or load_settings()
    client = client or labeled_bigquery_client(settings.gcp.project_id, "audit")

    payload = asdict(record)
    payload["error_summary"] = sanitize_error_message(payload.get("error_summary"))
    now = datetime.now(tz=UTC).isoformat()

    params: list[bigquery.ScalarQueryParameter] = []
    for key, value in payload.items():
        kind = "TIMESTAMP" if key in _TIMESTAMP_FIELDS else "STRING"
        params.append(bigquery.ScalarQueryParameter(key, kind, value))
    params.append(bigquery.ScalarQueryParameter("now", "TIMESTAMP", now))

    update_cols = [k for k in payload if k not in _KEY_FIELDS]
    set_clause = ", ".join(f"{col} = @{col}" for col in update_cols)
    insert_cols = ", ".join([*payload.keys(), "created_at", "updated_at"])
    insert_vals = ", ".join([f"@{col}" for col in payload] + ["@now", "@now"])

    sql = f"""
        MERGE `{_table_fqn(settings)}` AS target
        USING (SELECT @recovery_id AS recovery_id) AS source
        ON target.recovery_id = @recovery_id
        WHEN MATCHED THEN
          UPDATE SET {set_clause}, updated_at = @now
        WHEN NOT MATCHED THEN
          INSERT ({insert_cols})
          VALUES ({insert_vals})
    """
    client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()


def start_recovery_action(
    *,
    recovery_id: str,
    action_type: str,
    incident_id: str | None = None,
    scenario_id: str | None = None,
    pipeline_run_id: str | None = None,
    batch_id: str | None = None,
    deployment_id: str | None = None,
    operator: str | None = None,
    environment: str | None = None,
    source_state: str | None = None,
    target_state: str | None = None,
    git_sha: str | None = None,
    settings: AtlasSettings | None = None,
    client: bigquery.Client | None = None,
) -> RecoveryActionRecord:
    """Create or refresh a RUNNING recovery-action row."""
    record = RecoveryActionRecord(
        recovery_id=recovery_id,
        action_type=action_type,
        status="RUNNING",
        incident_id=incident_id,
        scenario_id=scenario_id,
        pipeline_run_id=pipeline_run_id,
        batch_id=batch_id,
        deployment_id=deployment_id,
        operator=operator,
        environment=environment,
        started_at=datetime.now(tz=UTC).isoformat(),
        source_state=source_state,
        target_state=target_state,
        verification_status="PENDING",
        git_sha=git_sha,
    )
    upsert_recovery_action(record, settings, client=client)
    emit_event(
        "recovery_action_started",
        severity="INFO",
        component="recovery",
        pipeline_run_id=pipeline_run_id,
        batch_id=batch_id,
        deployment_id=deployment_id,
        status="RUNNING",
        check_name=action_type,
        correlation_id=recovery_id,
    )
    return record


def finalize_recovery_action(
    record: RecoveryActionRecord,
    *,
    status: str,
    verification_status: str,
    error_type: str | None = None,
    error_summary: str | None = None,
    target_state: str | None = None,
    settings: AtlasSettings | None = None,
    client: bigquery.Client | None = None,
) -> RecoveryActionRecord:
    """Upsert the terminal state for one recovery attempt. Idempotent.

    SUCCESS is refused unless verification_status is VERIFIED — verification
    is not optional decoration on a recovery, it *is* the recovery evidence.
    """
    final = replace(
        record,
        status=status,
        verification_status=verification_status,
        completed_at=record.completed_at or datetime.now(tz=UTC).isoformat(),
        error_type=error_type,
        error_summary=error_summary,
        target_state=target_state or record.target_state,
    )
    upsert_recovery_action(final, settings, client=client)
    emit_event(
        "recovery_action_finalized",
        severity="INFO" if status == "SUCCESS" else "ERROR",
        component="recovery",
        pipeline_run_id=final.pipeline_run_id,
        batch_id=final.batch_id,
        deployment_id=final.deployment_id,
        status=status,
        check_name=final.action_type,
        correlation_id=final.recovery_id,
        error_type=error_type,
        error_message=error_summary,
    )
    return final


def query_recovery_actions(
    *,
    scenario_id: str | None = None,
    incident_id: str | None = None,
    batch_id: str | None = None,
    settings: AtlasSettings | None = None,
    client: bigquery.Client | None = None,
) -> list[dict[str, Any]]:
    """Return recovery actions filtered by scenario, incident, or batch."""
    settings = settings or load_settings()
    client = client or labeled_bigquery_client(settings.gcp.project_id, "audit")
    sql = f"""
        SELECT * FROM `{_table_fqn(settings)}`
        WHERE (@scenario_id IS NULL OR scenario_id = @scenario_id)
          AND (@incident_id IS NULL OR incident_id = @incident_id)
          AND (@batch_id IS NULL OR batch_id = @batch_id)
        ORDER BY started_at
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("scenario_id", "STRING", scenario_id),
            bigquery.ScalarQueryParameter("incident_id", "STRING", incident_id),
            bigquery.ScalarQueryParameter("batch_id", "STRING", batch_id),
        ]
    )
    return [dict(row) for row in client.query(sql, job_config=job_config).result()]
