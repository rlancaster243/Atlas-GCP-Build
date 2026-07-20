"""Run summary reconciliation for orchestrated pipeline finalization."""

from __future__ import annotations

from typing import Any


def reconcile_run_summary(
    local_summary: dict[str, Any],
    audit_row: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compare local JSON summary with the BigQuery audit row."""
    mismatches: list[str] = []
    if audit_row is None:
        mismatches.append("missing BigQuery audit row")
    else:
        for key in ("pipeline_run_id", "batch_id", "status"):
            if local_summary.get(key) != audit_row.get(key):
                mismatches.append(f"{key} mismatch")
    return {
        "reconciled": not mismatches,
        "mismatches": mismatches,
        "local_status": local_summary.get("status"),
        "audit_status": None if audit_row is None else audit_row.get("status"),
    }


def finalizer_should_fail(summary: dict[str, Any]) -> bool:
    """Return True when the all-done finalizer must raise to fail the DAG."""
    return summary.get("status") in {"FAILED", "PARTIAL"}
