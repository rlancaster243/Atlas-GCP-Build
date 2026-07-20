"""BigQuery operational audit records for orchestrated pipeline runs."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from google.cloud import bigquery

from atlas.config.settings import AtlasSettings, load_settings, table_fqn
from atlas.observability.cost import labeled_bigquery_client

ALLOWED_STATUSES = frozenset({"RUNNING", "SUCCESS", "FAILED", "PARTIAL"})
_SECRET_PATTERNS = (
    re.compile(r"BEGIN PRIVATE KEY"),
    # Redact the value that follows a private_key/client_email field, not just
    # the field name, so quoted JSON payloads cannot leak the secret itself.
    re.compile(r"private_key(_id)?\"?\s*[:=]\s*\"?[^\",}\s]*", re.IGNORECASE),
    re.compile(r"private_key(_id)?", re.IGNORECASE),
    re.compile(r"client_email\"?\s*[:=]\s*\"?[^\",}\s]*", re.IGNORECASE),
    re.compile(r"client_email", re.IGNORECASE),
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
)


@dataclass(frozen=True)
class PipelineRunRecord:
    """One durable audit row for an Airflow execution."""

    pipeline_run_id: str
    batch_id: str
    airflow_run_id: str
    dag_id: str
    processing_date: str
    started_at: str
    completed_at: str | None
    status: str
    attempt_number: int
    gcs_uri: str | None = None
    rows_generated: int | None = None
    rows_loaded: int | None = None
    rows_accepted: int | None = None
    rows_rejected: int | None = None
    fact_rows: int | None = None
    mart_event_count: int | None = None
    failed_task_id: str | None = None
    error_type: str | None = None
    error_message: str | None = None


def sanitize_error_message(message: str | None, *, max_length: int = 2000) -> str | None:
    """Remove sensitive values and truncate operational error text."""
    if not message:
        return None
    sanitized = message
    for pattern in _SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    sanitized = sanitized.strip()
    if len(sanitized) > max_length:
        return sanitized[: max_length - 3] + "..."
    return sanitized or None


def _table_fqn(settings: AtlasSettings) -> str:
    return f"{settings.gcp.project_id}.atlas_ops.pipeline_runs"


def upsert_pipeline_run(
    record: PipelineRunRecord,
    settings: AtlasSettings | None = None,
    *,
    client: bigquery.Client | None = None,
) -> None:
    """Merge one pipeline run audit row keyed by pipeline_run_id."""
    if record.status not in ALLOWED_STATUSES:
        raise ValueError(f"Unsupported audit status: {record.status}")
    settings = settings or load_settings()
    bq_client = client or labeled_bigquery_client(settings.gcp.project_id, "audit")
    query = f"""
        MERGE `{_table_fqn(settings)}` AS target
        USING (
          SELECT
            @pipeline_run_id AS pipeline_run_id,
            @batch_id AS batch_id,
            @airflow_run_id AS airflow_run_id,
            @dag_id AS dag_id,
            DATE(@processing_date) AS processing_date,
            TIMESTAMP(@started_at) AS started_at,
            TIMESTAMP(@completed_at) AS completed_at,
            @status AS status,
            @attempt_number AS attempt_number,
            @gcs_uri AS gcs_uri,
            @rows_generated AS rows_generated,
            @rows_loaded AS rows_loaded,
            @rows_accepted AS rows_accepted,
            @rows_rejected AS rows_rejected,
            @fact_rows AS fact_rows,
            @mart_event_count AS mart_event_count,
            @failed_task_id AS failed_task_id,
            @error_type AS error_type,
            @error_message AS error_message
        ) AS source
        ON target.pipeline_run_id = source.pipeline_run_id
        WHEN MATCHED THEN UPDATE SET
          batch_id = source.batch_id,
          airflow_run_id = source.airflow_run_id,
          dag_id = source.dag_id,
          processing_date = source.processing_date,
          completed_at = source.completed_at,
          status = source.status,
          attempt_number = source.attempt_number,
          gcs_uri = source.gcs_uri,
          rows_generated = source.rows_generated,
          rows_loaded = source.rows_loaded,
          rows_accepted = source.rows_accepted,
          rows_rejected = source.rows_rejected,
          fact_rows = source.fact_rows,
          mart_event_count = source.mart_event_count,
          failed_task_id = source.failed_task_id,
          error_type = source.error_type,
          error_message = source.error_message,
          updated_at = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN INSERT (
          pipeline_run_id,
          batch_id,
          airflow_run_id,
          dag_id,
          processing_date,
          started_at,
          completed_at,
          status,
          attempt_number,
          gcs_uri,
          rows_generated,
          rows_loaded,
          rows_accepted,
          rows_rejected,
          fact_rows,
          mart_event_count,
          failed_task_id,
          error_type,
          error_message,
          created_at,
          updated_at
        ) VALUES (
          source.pipeline_run_id,
          source.batch_id,
          source.airflow_run_id,
          source.dag_id,
          source.processing_date,
          source.started_at,
          source.completed_at,
          source.status,
          source.attempt_number,
          source.gcs_uri,
          source.rows_generated,
          source.rows_loaded,
          source.rows_accepted,
          source.rows_rejected,
          source.fact_rows,
          source.mart_event_count,
          source.failed_task_id,
          source.error_type,
          source.error_message,
          CURRENT_TIMESTAMP(),
          CURRENT_TIMESTAMP()
        )
    """
    params = asdict(record)
    params["error_message"] = sanitize_error_message(record.error_message)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter(name, _param_type(name, value), value)
            for name, value in params.items()
        ]
    )
    bq_client.query(query, job_config=job_config).result()


# Integer-typed audit columns: a NULL value must still carry the INT64 type so the
# MERGE source column matches the target schema (a STRING NULL cannot be assigned
# to an INT64 column in BigQuery).
_INT64_FIELDS = frozenset(
    {
        "attempt_number",
        "rows_generated",
        "rows_loaded",
        "rows_accepted",
        "rows_rejected",
        "fact_rows",
        "mart_event_count",
    }
)


def _param_type(name: str, value: Any) -> str:
    if isinstance(value, bool):
        return "BOOL"
    if isinstance(value, int):
        return "INT64"
    if name in _INT64_FIELDS:
        return "INT64"
    return "STRING"


def start_pipeline_run(
    *,
    pipeline_run_id: str,
    batch_id: str,
    airflow_run_id: str,
    dag_id: str,
    processing_date: str,
    attempt_number: int = 1,
    settings: AtlasSettings | None = None,
    client: bigquery.Client | None = None,
) -> PipelineRunRecord:
    """Create or refresh a RUNNING audit row."""
    started_at = datetime.now(tz=UTC).isoformat()
    record = PipelineRunRecord(
        pipeline_run_id=pipeline_run_id,
        batch_id=batch_id,
        airflow_run_id=airflow_run_id,
        dag_id=dag_id,
        processing_date=processing_date,
        started_at=started_at,
        completed_at=None,
        status="RUNNING",
        attempt_number=attempt_number,
    )
    upsert_pipeline_run(record, settings=settings, client=client)
    return record


def finalize_pipeline_run(
    record: PipelineRunRecord,
    *,
    settings: AtlasSettings | None = None,
    client: bigquery.Client | None = None,
) -> PipelineRunRecord:
    """Upsert the terminal audit state for one execution."""
    completed = record.completed_at or datetime.now(tz=UTC).isoformat()
    final_record = PipelineRunRecord(**{**asdict(record), "completed_at": completed})
    upsert_pipeline_run(final_record, settings=settings, client=client)
    return final_record


def query_pipeline_run(
    pipeline_run_id: str,
    settings: AtlasSettings | None = None,
    *,
    client: bigquery.Client | None = None,
) -> dict[str, Any] | None:
    """Fetch one audit row as a dictionary."""
    settings = settings or load_settings()
    bq_client = client or labeled_bigquery_client(settings.gcp.project_id, "audit")
    query = f"""
        SELECT *
        FROM `{_table_fqn(settings)}`
        WHERE pipeline_run_id = @pipeline_run_id
        LIMIT 1
    """
    rows = list(
        bq_client.query(
            query,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter("pipeline_run_id", "STRING", pipeline_run_id)]
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


def collect_batch_metrics(
    batch_id: str,
    *,
    settings: AtlasSettings | None = None,
    client: bigquery.Client | None = None,
    dbt_dataset: str | None = None,
) -> dict[str, int]:
    """Return best-effort batch-scoped row counts for the audit record.

    Each COUNT is guarded independently: a missing relation or query error
    yields an absent metric rather than raising, so populating audit volumes can
    never fail the finalizer. int_rejected_events lives in the quarantine schema;
    the other relations follow the {dbt_dataset}_{folder} layout.
    """
    settings = settings or load_settings()
    bq_client = client or labeled_bigquery_client(settings.gcp.project_id, "audit")
    dataset = dbt_dataset or os.environ.get("ATLAS_DBT_DATASET", "atlas")
    project = settings.gcp.project_id
    relations = {
        "rows_loaded": table_fqn(settings),
        "rows_accepted": f"{project}.{dataset}_intermediate.int_accepted_events",
        "rows_rejected": f"{project}.{dataset}_quarantine.int_rejected_events",
        "fact_rows": f"{project}.{dataset}_core.fct_events",
    }
    metrics: dict[str, int] = {}
    for metric, relation in relations.items():
        try:
            rows = list(
                bq_client.query(
                    f"SELECT COUNT(1) AS n FROM `{relation}` WHERE batch_id = @batch_id",
                    job_config=bigquery.QueryJobConfig(
                        query_parameters=[bigquery.ScalarQueryParameter("batch_id", "STRING", batch_id)]
                    ),
                ).result()
            )
            metrics[metric] = int(rows[0]["n"]) if rows else 0
        except Exception:  # noqa: BLE001 - metrics are best-effort observability
            continue
    return metrics


def write_local_run_summary(
    pipeline_run_id: str,
    payload: dict[str, Any],
    settings: AtlasSettings | None = None,
) -> str:
    """Persist detailed task-level evidence beside Airflow logs."""
    settings = settings or load_settings()
    summary_dir = settings.logging.log_dir / "airflow" / pipeline_run_id
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_path = summary_dir / "run-summary.json"
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(summary_path)
