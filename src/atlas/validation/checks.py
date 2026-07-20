"""Validation engine for Project Atlas Sprint 1.

Purpose:
    Evaluate loaded raw events and emit PASS/FAIL with detailed check results.

Interactions:
    Queries ``atlas_raw.events`` after load and compares findings against the
    seeded anomaly profile for acceptance testing.

Engineering principles:
    - Fail loudly on unexpected data quality issues.
    - Treat expected seeded anomalies as validation failures overall, while
      acceptance tests verify each expected defect was detected.

Common failure modes:
    - Row count mismatch versus generated file.
    - Missing partition rows for the primary event_date.
    - Duplicate event_id count lower than seeded profile.

Implementation choice:
    SQL-first validation keeps checks close to the warehouse and prepares for
    dbt tests in v0.3. Alternatives considered: pandas validation (extra runtime
    dependency in Cloud Shell) and Great Expectations (future phase).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from google.cloud import bigquery

from atlas.config.settings import AtlasSettings, table_fqn
from atlas.observability.cost import labeled_bigquery_client


@dataclass(frozen=True)
class ValidationCheck:
    """Result of an individual validation check."""

    name: str
    status: str
    expected: Any
    actual: Any
    message: str


@dataclass(frozen=True)
class ValidationReport:
    """Aggregate validation report for a pipeline run."""

    pipeline_run_id: str
    overall_status: str
    checks: list[ValidationCheck]

    def to_dict(self) -> dict[str, Any]:
        """Convert the report to a JSON-serializable dictionary."""
        return {
            "pipeline_run_id": self.pipeline_run_id,
            "overall_status": self.overall_status,
            "checks": [
                {
                    "name": check.name,
                    "status": check.status,
                    "expected": check.expected,
                    "actual": check.actual,
                    "message": check.message,
                }
                for check in self.checks
            ],
        }


def _query_scalar(client: bigquery.Client, sql: str, params: dict[str, Any] | None = None) -> Any:
    """Execute a scalar query and return the first column of the first row."""
    query_params: list[bigquery.ScalarQueryParameter | bigquery.ArrayQueryParameter] = []
    for name, value in (params or {}).items():
        if isinstance(value, bool):
            param_type = "BOOL"
        elif isinstance(value, int):
            param_type = "INT64"
        elif isinstance(value, list):
            param_type = "STRING"
            value = value
        else:
            param_type = "STRING"
        if isinstance(value, list):
            query_params.append(bigquery.ArrayQueryParameter(name, "STRING", value))
        else:
            query_params.append(bigquery.ScalarQueryParameter(name, param_type, value))
    rows = list(
        client.query(
            sql,
            job_config=bigquery.QueryJobConfig(query_parameters=query_params),
        ).result()
    )
    if not rows:
        return None
    return next(iter(rows[0].values()))


def _exact_match(actual: Any, expected: int) -> bool:
    """Return True when an observed anomaly count matches the seeded profile."""
    return actual == expected


def validate_loaded_run(
    settings: AtlasSettings,
    pipeline_run_id: str,
    primary_event_date: str,
    *,
    client: bigquery.Client | None = None,
    batch_id: str | None = None,
    processing_date: str | None = None,
    mode: str = "sprint1",
) -> ValidationReport:
    """Validate a loaded pipeline run and return PASS/FAIL results.

    When ``batch_id`` is provided (Airflow mode), scope checks to the stable batch
    identifier and compare future-dated rows against ``processing_date``.
    """
    bq_client = client or labeled_bigquery_client(settings.gcp.project_id, "validation")
    target = table_fqn(settings)
    profile = settings.anomaly_profile
    checks: list[ValidationCheck] = []

    if batch_id is not None:
        scope_filter = "batch_id = @batch_id"
        scope_params: dict[str, Any] = {"batch_id": batch_id}
        report_id = batch_id
    else:
        scope_filter = "pipeline_run_id = @run_id"
        scope_params = {"run_id": pipeline_run_id}
        report_id = pipeline_run_id

    row_count = _query_scalar(
        bq_client,
        f"SELECT COUNT(1) AS value FROM `{target}` WHERE {scope_filter}",
        scope_params,
    )
    checks.append(
        ValidationCheck(
            name="row_count",
            status="PASS" if row_count == settings.validation.expected_event_count else "FAIL",
            expected=settings.validation.expected_event_count,
            actual=row_count,
            message="Loaded row count matches generated event count.",
        )
    )

    partition_count = _query_scalar(
        bq_client,
        f"""
        SELECT COUNT(1) AS value
        FROM `{target}`
        WHERE {scope_filter}
          AND event_date = DATE(@event_date)
        """,
        {**scope_params, "event_date": primary_event_date},
    )
    checks.append(
        ValidationCheck(
            name="partition_presence",
            status="PASS" if partition_count and partition_count > 0 else "FAIL",
            expected=f">0 rows for {primary_event_date}",
            actual=partition_count,
            message="Primary partition contains rows for the run.",
        )
    )

    schema_ok = _query_scalar(
        bq_client,
        f"""
        SELECT COUNT(1) = 0 AS value
        FROM `{target}`
        WHERE {scope_filter}
          AND (
            event_id IS NULL
            OR event_name IS NULL
            OR event_timestamp IS NULL
            OR event_date IS NULL
            OR ingested_at IS NULL
            OR source_file IS NULL
            OR pipeline_run_id IS NULL
          )
        """,
        scope_params,
    )
    checks.append(
        ValidationCheck(
            name="schema_required_fields",
            status="PASS" if schema_ok else "FAIL",
            expected=True,
            actual=bool(schema_ok),
            message="Required non-null columns are populated.",
        )
    )

    if batch_id is not None:
        batch_id_present = _query_scalar(
            bq_client,
            f"""
            SELECT COUNT(1) AS value
            FROM `{target}`
            WHERE {scope_filter}
              AND batch_id IS NULL
            """,
            scope_params,
        )
        checks.append(
            ValidationCheck(
                name="batch_id_populated",
                status="PASS" if batch_id_present == 0 else "FAIL",
                expected=0,
                actual=batch_id_present,
                message="All batch-scoped rows carry batch_id.",
            )
        )

    distinct_event_ids = _query_scalar(
        bq_client,
        f"""
        SELECT COUNT(DISTINCT event_id) AS value
        FROM `{target}`
        WHERE {scope_filter}
        """,
        scope_params,
    )
    duplicate_rows = (row_count or 0) - (distinct_event_ids or 0)
    expected_duplicate_groups = profile.expected_count("duplicate_event_ids") // 2
    checks.append(
        ValidationCheck(
            name="distinct_event_ids",
            status="PASS"
            if distinct_event_ids == settings.validation.expected_event_count - expected_duplicate_groups
            else "FAIL",
            expected=settings.validation.expected_event_count - expected_duplicate_groups,
            actual=distinct_event_ids,
            message="Distinct event_id count reconciles with duplicate rows.",
        )
    )
    checks.append(
        ValidationCheck(
            name="duplicate_rows",
            status="PASS" if duplicate_rows == expected_duplicate_groups else "FAIL",
            expected=expected_duplicate_groups,
            actual=duplicate_rows,
            message="Duplicate physical rows reconcile with seeded duplicate event_ids.",
        )
    )

    duplicate_count = _query_scalar(
        bq_client,
        f"""
        SELECT COUNT(1) AS value
        FROM (
          SELECT event_id
          FROM `{target}`
          WHERE {scope_filter}
          GROUP BY event_id
          HAVING COUNT(1) > 1
        )
        """,
        scope_params,
    )
    expected_duplicates = profile.expected_count("duplicate_event_ids")
    checks.append(
        ValidationCheck(
            name="duplicates",
            status="FAIL" if duplicate_count else "PASS",
            expected=f"detect {expected_duplicates // 2} duplicate id groups",
            actual=duplicate_count,
            message="Duplicate event_id values detected.",
        )
    )

    null_user_ids = _query_scalar(
        bq_client,
        f"""
        SELECT COUNT(1) AS value
        FROM `{target}`
        WHERE {scope_filter}
          AND user_id IS NULL
        """,
        scope_params,
    )
    expected_null_users = profile.expected_count("null_user_ids")
    checks.append(
        ValidationCheck(
            name="null_user_ids",
            status="FAIL" if null_user_ids else "PASS",
            expected=f"detect {expected_null_users} null user_id rows",
            actual=null_user_ids,
            message="Null user_id values detected.",
        )
    )

    invalid_countries = _query_scalar(
        bq_client,
        f"""
        SELECT COUNT(1) AS value
        FROM `{target}`
        WHERE {scope_filter}
          AND country_code NOT IN UNNEST(@valid_countries)
        """,
        {
            **scope_params,
            "valid_countries": profile.valid_country_codes,
        },
    )
    expected_invalid_countries = profile.expected_count("invalid_country_codes")
    checks.append(
        ValidationCheck(
            name="invalid_country_codes",
            status="FAIL" if invalid_countries else "PASS",
            expected=f"detect {expected_invalid_countries} invalid countries",
            actual=invalid_countries,
            message="Invalid country_code values detected.",
        )
    )

    if batch_id is not None and processing_date is not None:
        future_timestamps = _query_scalar(
            bq_client,
            f"""
            SELECT COUNT(1) AS value
            FROM `{target}`
            WHERE {scope_filter}
              AND event_date > DATE(@processing_date)
            """,
            {**scope_params, "processing_date": processing_date},
        )
    else:
        future_timestamps = _query_scalar(
            bq_client,
            f"""
            SELECT COUNT(1) AS value
            FROM `{target}`
            WHERE {scope_filter}
              AND event_date > CURRENT_DATE()
            """,
            scope_params,
        )
    expected_future = profile.expected_count("future_timestamps")
    checks.append(
        ValidationCheck(
            name="future_timestamps",
            status="FAIL" if future_timestamps else "PASS",
            expected=f"detect {expected_future} future-dated rows",
            actual=future_timestamps,
            message="Future calendar-date event_date values detected.",
        )
    )

    other_partition_rows = _query_scalar(
        bq_client,
        f"""
        SELECT COUNT(1) AS value
        FROM `{target}`
        WHERE {scope_filter}
          AND event_date != DATE(@event_date)
        """,
        {**scope_params, "event_date": primary_event_date},
    )
    checks.append(
        ValidationCheck(
            name="partition_reconciliation",
            status="PASS"
            if (partition_count or 0) + (other_partition_rows or 0) == (row_count or 0)
            else "FAIL",
            expected={
                "primary_event_date_rows": partition_count,
                "other_partition_rows": other_partition_rows,
                "total_rows": row_count,
            },
            actual={
                "primary_event_date_rows": partition_count,
                "other_partition_rows": other_partition_rows,
                "total_rows": row_count,
            },
            message=("Primary-partition rows plus other-partition rows reconcile to total row count."),
        )
    )

    late_arrivals = _query_scalar(
        bq_client,
        f"""
        SELECT COUNT(1) AS value
        FROM `{target}`
        WHERE {scope_filter}
          AND event_date < DATE(event_timestamp)
        """,
        scope_params,
    )
    expected_late = profile.expected_count("late_arriving_events")
    checks.append(
        ValidationCheck(
            name="late_arriving_events",
            status="FAIL" if late_arrivals else "PASS",
            expected=f"detect {expected_late} late-arriving rows",
            actual=late_arrivals,
            message="Late-arriving event_date values detected.",
        )
    )

    if mode == "airflow" and batch_id is not None:
        overall_status = (
            "PASS"
            if all(
                check.status == "PASS"
                for check in checks
                if check.name
                not in {
                    "duplicates",
                    "null_user_ids",
                    "invalid_country_codes",
                    "future_timestamps",
                    "late_arriving_events",
                }
            )
            else "FAIL"
        )
    else:
        overall_status = "PASS" if all(check.status == "PASS" for check in checks) else "FAIL"

    return ValidationReport(
        pipeline_run_id=report_id,
        overall_status=overall_status,
        checks=checks,
    )


def validate_anomaly_detection(report: ValidationReport, settings: AtlasSettings) -> ValidationReport:
    """Build acceptance-oriented checks proving expected anomalies were detected."""
    profile = settings.anomaly_profile
    by_name = {check.name: check for check in report.checks}
    acceptance_checks = []

    duplicate_actual = by_name["duplicates"].actual or 0
    expected_duplicate_groups = profile.expected_count("duplicate_event_ids") // 2
    acceptance_checks.append(
        ValidationCheck(
            name="acceptance_duplicate_detection",
            status="PASS" if _exact_match(duplicate_actual, expected_duplicate_groups) else "FAIL",
            expected=expected_duplicate_groups,
            actual=duplicate_actual,
            message="Expected duplicate event_id groups were detected exactly.",
        )
    )

    null_actual = by_name["null_user_ids"].actual or 0
    expected_null_users = profile.expected_count("null_user_ids")
    acceptance_checks.append(
        ValidationCheck(
            name="acceptance_null_user_detection",
            status="PASS" if _exact_match(null_actual, expected_null_users) else "FAIL",
            expected=expected_null_users,
            actual=null_actual,
            message="Expected null user_id rows were detected exactly.",
        )
    )

    invalid_country_actual = by_name["invalid_country_codes"].actual or 0
    expected_invalid_countries = profile.expected_count("invalid_country_codes")
    acceptance_checks.append(
        ValidationCheck(
            name="acceptance_invalid_country_detection",
            status="PASS" if _exact_match(invalid_country_actual, expected_invalid_countries) else "FAIL",
            expected=expected_invalid_countries,
            actual=invalid_country_actual,
            message="Expected invalid country_code rows were detected exactly.",
        )
    )

    future_actual = by_name["future_timestamps"].actual or 0
    expected_future = profile.expected_count("future_timestamps")
    acceptance_checks.append(
        ValidationCheck(
            name="acceptance_future_timestamp_detection",
            status="PASS" if _exact_match(future_actual, expected_future) else "FAIL",
            expected=expected_future,
            actual=future_actual,
            message="Expected future-dated rows were detected exactly.",
        )
    )

    late_actual = by_name["late_arriving_events"].actual or 0
    expected_late = profile.expected_count("late_arriving_events")
    acceptance_checks.append(
        ValidationCheck(
            name="acceptance_late_arrival_detection",
            status="PASS" if _exact_match(late_actual, expected_late) else "FAIL",
            expected=expected_late,
            actual=late_actual,
            message="Expected late-arriving rows were detected exactly.",
        )
    )

    merged_checks = report.checks + acceptance_checks
    return ValidationReport(
        pipeline_run_id=report.pipeline_run_id,
        overall_status=report.overall_status,
        checks=merged_checks,
    )
