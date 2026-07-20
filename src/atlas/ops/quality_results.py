"""Durable data-quality and monitor-evaluation records (Sprint 5, Phase 4).

Two grains, two tables:

- ``atlas_ops.quality_results`` — one row per data-quality check per pipeline
  run (MERGE key: pipeline_run_id + check_name). Populated by the warehouse
  validator and any future check producers; dbt evidence is summarized and
  linked, not duplicated.
- ``atlas_ops.monitor_evaluations`` — one row per monitor check per
  evaluation window (MERGE key: evaluation_id). Populated by the
  atlas_observability_monitor DAG.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from google.cloud import bigquery

from atlas.config.settings import AtlasSettings, load_settings
from atlas.observability.cost import labeled_bigquery_client

ALLOWED_CHECK_CATEGORIES = frozenset(
    {
        "FRESHNESS",
        "COMPLETENESS",
        "UNIQUENESS",
        "REFERENTIAL_INTEGRITY",
        "SCHEMA",
        "VOLUME",
        "REJECTION_RATE",
        "RECONCILIATION",
    }
)
ALLOWED_QUALITY_STATUSES = frozenset({"PASS", "WARN", "FAIL", "NO_DATA"})
ALLOWED_EVALUATION_STATUSES = frozenset({"PASS", "WARN", "FAIL", "NO_DATA", "DISABLED"})
ALLOWED_SEVERITIES = frozenset({"INFO", "WARNING", "CRITICAL"})

_MAX_DETAILS_LENGTH = 4000


@dataclass(frozen=True)
class QualityResultRecord:
    """One durable data-quality check result."""

    pipeline_run_id: str
    check_name: str
    check_category: str
    severity: str
    status: str
    evaluated_at: str
    batch_id: str | None = None
    observed_value: float | None = None
    expected_value: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    model_name: str | None = None
    details_json: str | None = None
    git_sha: str | None = None


@dataclass(frozen=True)
class MonitorEvaluationRecord:
    """One durable monitor evaluation for a bounded window."""

    evaluation_id: str
    check_name: str
    environment: str
    status: str
    evaluated_at: str
    window_start: str | None = None
    window_end: str | None = None
    severity: str | None = None
    observed_value: float | None = None
    threshold: float | None = None
    incident_key: str | None = None
    source: str | None = None
    details_json: str | None = None


def _truncate_details(details_json: str | None) -> str | None:
    if details_json and len(details_json) > _MAX_DETAILS_LENGTH:
        return details_json[: _MAX_DETAILS_LENGTH - 3] + "..."
    return details_json


def details_to_json(details: dict[str, Any] | None) -> str | None:
    """Serialize a details dict defensively (non-serializable -> repr)."""
    if not details:
        return None
    return _truncate_details(json.dumps(details, default=repr, sort_keys=True))


_QUALITY_FLOAT_FIELDS = frozenset({"observed_value", "expected_value", "lower_bound", "upper_bound"})
_EVAL_FLOAT_FIELDS = frozenset({"observed_value", "threshold"})


def _merge(
    table: str,
    payload: dict[str, Any],
    key_fields: tuple[str, ...],
    float_fields: frozenset[str],
    timestamp_fields: frozenset[str],
    client: bigquery.Client,
) -> None:
    now = datetime.now(tz=UTC).isoformat()
    params: list[bigquery.ScalarQueryParameter] = []
    for key, value in payload.items():
        if key in float_fields:
            params.append(bigquery.ScalarQueryParameter(key, "FLOAT64", value))
        elif key in timestamp_fields:
            params.append(bigquery.ScalarQueryParameter(key, "TIMESTAMP", value))
        else:
            params.append(bigquery.ScalarQueryParameter(key, "STRING", value))
    params.append(bigquery.ScalarQueryParameter("now", "TIMESTAMP", now))

    on_clause = " AND ".join(f"target.{k} = @{k}" for k in key_fields)
    update_cols = [k for k in payload if k not in key_fields]
    set_clause = ", ".join(f"{col} = @{col}" for col in update_cols)
    insert_cols = ", ".join([*payload.keys(), "created_at", "updated_at"])
    insert_vals = ", ".join([f"@{col}" for col in payload] + ["@now", "@now"])
    sql = f"""
        MERGE `{table}` AS target
        USING (SELECT @{key_fields[0]} AS join_key) AS source
        ON {on_clause}
        WHEN MATCHED THEN
          UPDATE SET {set_clause}, updated_at = @now
        WHEN NOT MATCHED THEN
          INSERT ({insert_cols})
          VALUES ({insert_vals})
    """
    client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()


def upsert_quality_result(
    record: QualityResultRecord,
    settings: AtlasSettings | None = None,
    *,
    client: bigquery.Client | None = None,
) -> None:
    """Merge one quality result keyed by (pipeline_run_id, check_name)."""
    if record.check_category not in ALLOWED_CHECK_CATEGORIES:
        raise ValueError(f"Unsupported check category: {record.check_category}")
    if record.status not in ALLOWED_QUALITY_STATUSES:
        raise ValueError(f"Unsupported quality status: {record.status}")
    if record.severity not in ALLOWED_SEVERITIES:
        raise ValueError(f"Unsupported severity: {record.severity}")
    settings = settings or load_settings()
    client = client or labeled_bigquery_client(settings.gcp.project_id, "audit")
    payload = asdict(record)
    payload["details_json"] = _truncate_details(payload.get("details_json"))
    _merge(
        f"{settings.gcp.project_id}.atlas_ops.quality_results",
        payload,
        ("pipeline_run_id", "check_name"),
        _QUALITY_FLOAT_FIELDS,
        frozenset({"evaluated_at"}),
        client,
    )


def upsert_monitor_evaluation(
    record: MonitorEvaluationRecord,
    settings: AtlasSettings | None = None,
    *,
    client: bigquery.Client | None = None,
) -> None:
    """Merge one monitor evaluation keyed by evaluation_id."""
    if record.status not in ALLOWED_EVALUATION_STATUSES:
        raise ValueError(f"Unsupported evaluation status: {record.status}")
    if record.severity is not None and record.severity not in ALLOWED_SEVERITIES:
        raise ValueError(f"Unsupported severity: {record.severity}")
    settings = settings or load_settings()
    client = client or labeled_bigquery_client(settings.gcp.project_id, "audit")
    payload = asdict(record)
    payload["details_json"] = _truncate_details(payload.get("details_json"))
    _merge(
        f"{settings.gcp.project_id}.atlas_ops.monitor_evaluations",
        payload,
        ("evaluation_id",),
        _EVAL_FLOAT_FIELDS,
        frozenset({"evaluated_at", "window_start", "window_end"}),
        client,
    )
