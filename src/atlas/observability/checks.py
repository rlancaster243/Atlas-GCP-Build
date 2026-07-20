"""Bridge warehouse validation results into durable quality records (Phase 4).

The Sprint 4 warehouse validator (atlas.validation.warehouse) computes ten
batch-scoped reconciliation checks and returns a WarehouseReport. Sprint 5
persists each check into ``atlas_ops.quality_results`` so correctness
evidence survives the task log. dbt test evidence is summarized here, not
re-implemented: the dbt_build task already fails on test failures, and the
reconciliation checks verify the resulting tables directly.
"""

from __future__ import annotations

import numbers
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from atlas.config.settings import AtlasSettings
from atlas.observability.logging import emit_event
from atlas.ops.quality_results import (
    QualityResultRecord,
    details_to_json,
    upsert_quality_result,
)

if TYPE_CHECKING:
    from google.cloud import bigquery

    from atlas.validation.warehouse import WarehouseReport

# Category mapping for the warehouse reconciliation checks (ADR-011 Plane 1).
CHECK_CATEGORIES: dict[str, str] = {
    "batch_nonempty": "COMPLETENESS",
    "raw_equals_classification": "RECONCILIATION",
    "accepted_plus_rejected_equals_raw": "RECONCILIATION",
    "accepted_equals_fact": "RECONCILIATION",
    "fact_event_ids_unique": "UNIQUENESS",
    "fact_user_fk_resolves": "REFERENTIAL_INTEGRITY",
    "fact_country_fk_resolves": "REFERENTIAL_INTEGRITY",
    "mart_totals_reconcile": "RECONCILIATION",
    "processing_date_semantics": "COMPLETENESS",
    "batch_lineage_semantics": "COMPLETENESS",
}
_DEFAULT_CATEGORY = "RECONCILIATION"


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        return None
    return float(value)


def persist_warehouse_report(
    report: WarehouseReport,
    pipeline_run_id: str,
    *,
    git_sha: str | None = None,
    settings: AtlasSettings | None = None,
    client: bigquery.Client | None = None,
) -> int:
    """Write one quality_results row per warehouse check; returns rows written.

    Persistence is telemetry: failures emit a structured error and are
    reported, but never mask the validation outcome itself.
    """
    written = 0
    evaluated_at = datetime.now(tz=UTC).isoformat()
    for check in report.checks:
        record = QualityResultRecord(
            pipeline_run_id=pipeline_run_id,
            batch_id=report.batch_id,
            check_name=check.name,
            check_category=CHECK_CATEGORIES.get(check.name, _DEFAULT_CATEGORY),
            severity="CRITICAL" if check.status == "FAIL" else "INFO",
            status=check.status,
            evaluated_at=evaluated_at,
            observed_value=_as_float(check.actual),
            expected_value=_as_float(check.expected),
            details_json=details_to_json(
                {"message": check.message, "expected": check.expected, "actual": check.actual}
            ),
            git_sha=git_sha,
        )
        try:
            upsert_quality_result(record, settings, client=client)
            written += 1
        except Exception as exc:  # noqa: BLE001 - telemetry must not mask validation
            emit_event(
                "quality_result_write_failed",
                severity="ERROR",
                component="quality_results",
                pipeline_run_id=pipeline_run_id,
                batch_id=report.batch_id,
                check_name=check.name,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
    emit_event(
        "warehouse_quality_persisted",
        severity="INFO" if written == len(report.checks) else "WARNING",
        component="quality_results",
        pipeline_run_id=pipeline_run_id,
        batch_id=report.batch_id,
        status=report.overall_status,
        details={"checks": len(report.checks), "persisted": written},
    )
    return written
