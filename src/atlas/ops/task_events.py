"""Task-attempt audit records (Sprint 5, Phase 3).

Grain: one row per (pipeline_run_id, task_id, attempt_number, event_type) in
``atlas_ops.task_events``, written with idempotent parameterized MERGE.
Repeated callbacks update the existing row instead of duplicating it, so a
failed attempt 1 and a successful attempt 2 remain distinguishable rows.

Telemetry-safety contract (ADR-011): ``record_task_event_safely`` never
raises — a telemetry failure emits a structured fallback event and returns
False, leaving the caller's data path untouched. The finalizer separately
verifies telemetry completeness so degradation stays visible.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from google.cloud import bigquery

from atlas.config.settings import AtlasSettings, load_settings
from atlas.observability.cost import labeled_bigquery_client
from atlas.observability.logging import emit_event
from atlas.ops.audit import sanitize_error_message

ALLOWED_EVENT_TYPES = frozenset({"STARTED", "RETRY", "SUCCESS", "FAILED", "SKIPPED", "UPSTREAM_FAILED"})

# Task ids the finalizer expects telemetry for on every non-skipped run.
EXPECTED_TERMINAL_TASKS = (
    "resolve_run_context",
    "ensure_audit_resources",
    "start_run_audit",
    "preflight_environment",
    "generate_events",
    "upload_events",
    "load_bigquery_raw",
    "validate_raw_load",
    "dbt_seed",
    "dbt_source_freshness",
    "dbt_build",
    "validate_warehouse",
    "publish_success_marker",
)


# Where a row's timing came from (Sprint 6, Phase 1). Ordered by preference.
TIMING_SOURCES = frozenset({"step_runner_clock", "airflow_task_instance", "finalizer_reconciliation"})
TIMING_CONFIDENCES = frozenset({"exact", "partial", "none"})


@dataclass(frozen=True)
class TaskEventRecord:
    """One durable task-attempt audit row."""

    pipeline_run_id: str
    task_id: str
    attempt_number: int
    event_type: str
    batch_id: str | None = None
    airflow_run_id: str | None = None
    dag_id: str | None = None
    status: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    operator_type: str | None = None
    environment: str | None = None
    git_sha: str | None = None
    rows_affected: int | None = None
    error_type: str | None = None
    error_message: str | None = None
    timing_source: str | None = None
    timing_confidence: str | None = None


def _table_fqn(settings: AtlasSettings) -> str:
    return f"{settings.gcp.project_id}.atlas_ops.task_events"


_INT64_FIELDS = frozenset({"attempt_number", "duration_ms", "rows_affected"})
_TIMESTAMP_FIELDS = frozenset({"started_at", "completed_at"})
_KEY_FIELDS = ("pipeline_run_id", "task_id", "attempt_number", "event_type")


def upsert_task_event(
    record: TaskEventRecord,
    settings: AtlasSettings | None = None,
    *,
    client: bigquery.Client | None = None,
) -> None:
    """Merge one task event row keyed by (run, task, attempt, event_type)."""
    if record.event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError(f"Unsupported task event type: {record.event_type}")
    if record.attempt_number < 1:
        raise ValueError("attempt_number must be >= 1")
    if record.timing_source is not None and record.timing_source not in TIMING_SOURCES:
        raise ValueError(f"Unsupported timing_source: {record.timing_source}")
    if record.timing_confidence is not None and record.timing_confidence not in TIMING_CONFIDENCES:
        raise ValueError(f"Unsupported timing_confidence: {record.timing_confidence}")

    settings = settings or load_settings()
    client = client or labeled_bigquery_client(settings.gcp.project_id, "audit")

    payload = asdict(record)
    payload["error_message"] = sanitize_error_message(payload.get("error_message"))
    now = datetime.now(tz=UTC).isoformat()

    params: list[bigquery.ScalarQueryParameter] = []
    for key, value in payload.items():
        if key in _INT64_FIELDS:
            params.append(bigquery.ScalarQueryParameter(key, "INT64", value))
        elif key in _TIMESTAMP_FIELDS:
            params.append(bigquery.ScalarQueryParameter(key, "TIMESTAMP", value))
        else:
            params.append(bigquery.ScalarQueryParameter(key, "STRING", value))
    params.append(bigquery.ScalarQueryParameter("now", "TIMESTAMP", now))

    update_cols = [k for k in payload if k not in _KEY_FIELDS]
    set_clause = ", ".join(f"{col} = @{col}" for col in update_cols)
    insert_cols = ", ".join([*payload.keys(), "created_at", "updated_at"])
    insert_vals = ", ".join([f"@{col}" for col in payload] + ["@now", "@now"])

    sql = f"""
        MERGE `{_table_fqn(settings)}` AS target
        USING (SELECT @pipeline_run_id AS pipeline_run_id) AS source
        ON target.pipeline_run_id = @pipeline_run_id
           AND target.task_id = @task_id
           AND target.attempt_number = @attempt_number
           AND target.event_type = @event_type
        WHEN MATCHED THEN
          UPDATE SET {set_clause}, updated_at = @now
        WHEN NOT MATCHED THEN
          INSERT ({insert_cols})
          VALUES ({insert_vals})
    """
    client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()


def record_task_event_safely(
    record: TaskEventRecord,
    settings: AtlasSettings | None = None,
    *,
    client: bigquery.Client | None = None,
) -> bool:
    """Write a task event without ever propagating telemetry failure.

    Returns True when the row was written. On failure, emits a structured
    ``task_telemetry_write_failed`` event and returns False.
    """
    try:
        upsert_task_event(record, settings, client=client)
        return True
    except Exception as exc:  # noqa: BLE001 - telemetry must not break the data path
        emit_event(
            "task_telemetry_write_failed",
            severity="ERROR",
            component="task_events",
            pipeline_run_id=record.pipeline_run_id,
            task_id=record.task_id,
            attempt_number=record.attempt_number,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        return False


def query_task_events(
    pipeline_run_id: str,
    settings: AtlasSettings | None = None,
    *,
    client: bigquery.Client | None = None,
) -> list[dict[str, Any]]:
    """Return all task events for one pipeline run, ordered for diagnosis."""
    settings = settings or load_settings()
    client = client or labeled_bigquery_client(settings.gcp.project_id, "audit")
    sql = f"""
        SELECT * FROM `{_table_fqn(settings)}`
        WHERE pipeline_run_id = @pipeline_run_id
        ORDER BY task_id, attempt_number, event_type
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("pipeline_run_id", "STRING", pipeline_run_id)]
    )
    return [dict(row) for row in client.query(sql, job_config=job_config).result()]


def telemetry_completeness(
    pipeline_run_id: str,
    settings: AtlasSettings | None = None,
    *,
    client: bigquery.Client | None = None,
    expected_tasks: tuple[str, ...] = EXPECTED_TERMINAL_TASKS,
) -> dict[str, Any]:
    """Report which expected tasks are missing a terminal event for a run.

    A task is "complete" when it has at least one terminal event
    (SUCCESS/FAILED/SKIPPED/UPSTREAM_FAILED). STARTED-only rows indicate the
    telemetry stream was cut mid-task.
    """
    events = query_task_events(pipeline_run_id, settings, client=client)
    terminal = {"SUCCESS", "FAILED", "SKIPPED", "UPSTREAM_FAILED"}
    seen_terminal = {e["task_id"] for e in events if e["event_type"] in terminal}
    started_only = {e["task_id"] for e in events if e["event_type"] == "STARTED"} - seen_terminal
    missing = [t for t in expected_tasks if t not in seen_terminal]
    return {
        "pipeline_run_id": pipeline_run_id,
        "complete": not missing,
        "missing_terminal": missing,
        "started_without_terminal": sorted(started_only),
        "event_count": len(events),
    }
