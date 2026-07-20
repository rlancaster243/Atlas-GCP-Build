"""Batch-scoped warehouse validation for the Airflow validate_warehouse step.

Purpose:
    Replace the Sprint 3 hardcoded PASS with real reconciliation between the
    raw layer, the dbt classification layer, the fact table, and the marts.

Interactions:
    Called by ``scripts/atlas_step_runner.py`` (step ``validate_warehouse``)
    after ``dbt_build`` succeeds. Queries BigQuery directly; it never mutates
    warehouse state.

Engineering principles:
    - Every check is batch-scoped where the model carries batch identity, so
      historical backfills validate identically to same-day runs.
    - The step fails loudly: any FAILed check makes the Airflow task fail.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from google.cloud import bigquery

from atlas.config.settings import AtlasSettings, load_settings, table_fqn
from atlas.observability.cost import labeled_bigquery_client


@dataclass(frozen=True)
class WarehouseCheck:
    """Result of one warehouse reconciliation check."""

    name: str
    status: str
    expected: Any
    actual: Any
    message: str


@dataclass(frozen=True)
class WarehouseReport:
    """Aggregate warehouse validation result for one batch."""

    batch_id: str
    overall_status: str
    checks: list[WarehouseCheck]

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "overall_status": self.overall_status,
            "checks": [
                {
                    "name": c.name,
                    "status": c.status,
                    "expected": c.expected,
                    "actual": c.actual,
                    "message": c.message,
                }
                for c in self.checks
            ],
        }


def _dbt_dataset_prefix() -> str:
    """Return the dbt target dataset prefix (default ``atlas``)."""
    return os.environ.get("ATLAS_DBT_DATASET", "atlas")


def warehouse_table(project_id: str, layer: str, table: str) -> str:
    """Return the fully qualified name of one dbt-managed warehouse table."""
    return f"{project_id}.{_dbt_dataset_prefix()}_{layer}.{table}"


def _scalar(client: bigquery.Client, sql: str, params: dict[str, str]) -> Any:
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter(name, "STRING", value) for name, value in params.items()
        ]
    )
    rows = list(client.query(sql, job_config=job_config).result())
    if not rows:
        return None
    return next(iter(rows[0].values()))


def validate_warehouse(
    batch_id: str,
    processing_date: str,
    settings: AtlasSettings | None = None,
    *,
    client: bigquery.Client | None = None,
) -> WarehouseReport:
    """Run batch-scoped reconciliation across raw, classification, fact, and marts."""
    settings = settings or load_settings()
    bq = client or labeled_bigquery_client(settings.gcp.project_id, "validation")
    project = settings.gcp.project_id
    raw = table_fqn(settings)
    classification = warehouse_table(project, "intermediate", "int_event_classification")
    accepted = warehouse_table(project, "intermediate", "int_accepted_events")
    rejected = warehouse_table(project, "quarantine", "int_rejected_events")
    fact = warehouse_table(project, "core", "fct_events")
    dim_users = warehouse_table(project, "core", "dim_users")
    dim_countries = warehouse_table(project, "core", "dim_countries")
    mart = warehouse_table(project, "marts", "mart_daily_event_metrics")
    scope = {"batch_id": batch_id}
    checks: list[WarehouseCheck] = []

    def add(name: str, passed: bool, expected: Any, actual: Any, message: str) -> None:
        checks.append(
            WarehouseCheck(
                name=name,
                status="PASS" if passed else "FAIL",
                expected=expected,
                actual=actual,
                message=message,
            )
        )

    raw_count = _scalar(bq, f"SELECT COUNT(1) FROM `{raw}` WHERE batch_id = @batch_id", scope)
    add(
        "batch_nonempty",
        bool(raw_count),
        "> 0 raw rows",
        raw_count,
        "The validated batch exists in the raw layer (guards against trivially passing on a missing batch).",
    )

    classified_count = _scalar(
        bq, f"SELECT COUNT(1) FROM `{classification}` WHERE batch_id = @batch_id", scope
    )
    add(
        "raw_equals_classification",
        raw_count == classified_count,
        raw_count,
        classified_count,
        "Every batch-scoped raw row is classified exactly once.",
    )

    accepted_count = _scalar(bq, f"SELECT COUNT(1) FROM `{accepted}` WHERE batch_id = @batch_id", scope)
    rejected_count = _scalar(bq, f"SELECT COUNT(1) FROM `{rejected}` WHERE batch_id = @batch_id", scope)
    add(
        "accepted_plus_rejected_equals_raw",
        (accepted_count or 0) + (rejected_count or 0) == (raw_count or 0),
        raw_count,
        {"accepted": accepted_count, "rejected": rejected_count},
        "Accepted plus rejected rows reconcile to the raw batch.",
    )

    fact_count = _scalar(
        bq,
        f"""
        SELECT COUNT(1)
        FROM `{fact}` f
        INNER JOIN `{accepted}` a USING (event_id)
        WHERE a.batch_id = @batch_id
        """,
        scope,
    )
    add(
        "accepted_equals_fact",
        fact_count == accepted_count,
        accepted_count,
        fact_count,
        "Batch-scoped fact rows reconcile to accepted events.",
    )

    duplicate_fact_ids = _scalar(
        bq,
        f"""
        SELECT COUNT(1)
        FROM (
          SELECT event_id
          FROM `{fact}`
          GROUP BY event_id
          HAVING COUNT(1) > 1
        )
        """,
        {},
    )
    add(
        "fact_event_ids_unique",
        duplicate_fact_ids == 0,
        0,
        duplicate_fact_ids,
        "fct_events.event_id is globally unique.",
    )

    orphan_users = _scalar(
        bq,
        f"""
        SELECT COUNT(1)
        FROM `{fact}` f
        LEFT JOIN `{dim_users}` u USING (user_id)
        WHERE f.user_id IS NOT NULL
          AND u.user_id IS NULL
        """,
        {},
    )
    add(
        "fact_user_fk_resolves",
        orphan_users == 0,
        0,
        orphan_users,
        "Every non-null fct_events.user_id resolves in dim_users.",
    )

    orphan_countries = _scalar(
        bq,
        f"""
        SELECT COUNT(1)
        FROM `{fact}` f
        LEFT JOIN `{dim_countries}` c USING (country_code)
        WHERE c.country_code IS NULL
        """,
        {},
    )
    add(
        "fact_country_fk_resolves",
        orphan_countries == 0,
        0,
        orphan_countries,
        "Every fct_events.country_code resolves in dim_countries.",
    )

    mart_total = _scalar(bq, f"SELECT COALESCE(SUM(event_count), 0) FROM `{mart}`", {})
    fact_total = _scalar(bq, f"SELECT COUNT(1) FROM `{fact}`", {})
    add(
        "mart_totals_reconcile",
        mart_total == fact_total,
        fact_total,
        mart_total,
        "mart_daily_event_metrics total event_count equals fct_events row count.",
    )

    bad_processing_dates = _scalar(
        bq,
        f"""
        SELECT COUNT(1)
        FROM `{raw}`
        WHERE batch_id = @batch_id
          AND (processing_date IS NULL OR processing_date != DATE(@processing_date))
        """,
        {**scope, "processing_date": processing_date},
    )
    add(
        "processing_date_semantics",
        bad_processing_dates == 0,
        0,
        bad_processing_dates,
        "Every batch-scoped raw row carries the batch's logical processing_date.",
    )

    null_batch_ids = _scalar(
        bq,
        f"""
        SELECT COUNT(1)
        FROM `{classification}`
        WHERE batch_id = @batch_id
          AND (event_id IS NULL OR pipeline_run_id IS NULL)
        """,
        scope,
    )
    add(
        "batch_lineage_semantics",
        null_batch_ids == 0,
        0,
        null_batch_ids,
        "Batch-scoped classification rows carry event and pipeline lineage.",
    )

    overall = "PASS" if all(c.status == "PASS" for c in checks) else "FAIL"
    return WarehouseReport(batch_id=batch_id, overall_status=overall, checks=checks)
