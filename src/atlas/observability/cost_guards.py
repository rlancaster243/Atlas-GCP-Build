"""BigQuery cost guardrails (Sprint 6, Phase 12).

Guards fail *before* material spend:

- ``estimate_query_bytes``    — dry-run estimate (bills nothing)
- ``enforce_dry_run_ceiling`` — refuse queries whose estimate exceeds the ceiling
- ``guarded_query_config``    — hard ``maximum_bytes_billed`` enforcement
- ``validate_backfill_window`` — bounded backfill windows, explicit override only
- ``require_full_refresh_approval`` — full refresh is an approved exception,
  never a default

Every rejection raises ``CostGuardViolation`` with the evidence (estimated
bytes, requested window) so the responsible component is identifiable without
running the expensive work.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

from google.cloud import bigquery

from atlas.observability.logging import emit_event

# Initial operational ceilings for the synthetic Atlas workload (not SLOs).
# A full scan of every Atlas dataset today is < 100 MB; 1 GiB catches an
# unpartitioned-scan mistake with an order-of-magnitude margin.
DEFAULT_MAX_ESTIMATED_BYTES = 1 * 1024**3
DEFAULT_MAX_BACKFILL_DAYS = 7
FULL_REFRESH_APPROVAL_VAR = "ATLAS_APPROVE_FULL_REFRESH"
BACKFILL_OVERRIDE_VAR = "ATLAS_APPROVE_UNBOUNDED_BACKFILL"


class CostGuardViolation(RuntimeError):
    """A guarded operation would exceed its cost boundary."""


def estimate_query_bytes(client: bigquery.Client, sql: str) -> int:
    """Dry-run a query and return the estimated bytes processed (bills $0)."""
    job = client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
    return int(job.total_bytes_processed or 0)


def enforce_dry_run_ceiling(
    client: bigquery.Client,
    sql: str,
    *,
    max_estimated_bytes: int = DEFAULT_MAX_ESTIMATED_BYTES,
    component: str = "adhoc",
) -> int:
    """Refuse execution when the dry-run estimate exceeds the ceiling.

    Returns the estimate so callers can record it as evidence.
    """
    estimated = estimate_query_bytes(client, sql)
    if estimated > max_estimated_bytes:
        emit_event(
            "cost_guard_blocked",
            severity="ERROR",
            component=component,
            check_name="dry_run_ceiling",
            observed_value=estimated,
            threshold=max_estimated_bytes,
            status="BLOCKED",
        )
        raise CostGuardViolation(
            f"query estimate {estimated} bytes exceeds ceiling {max_estimated_bytes} bytes; "
            "add a partition filter or raise the ceiling with documented approval"
        )
    return estimated


def guarded_query_config(
    *,
    maximum_bytes_billed: int = DEFAULT_MAX_ESTIMATED_BYTES,
    labels: dict[str, str] | None = None,
) -> bigquery.QueryJobConfig:
    """Job config that hard-fails the query at the BigQuery layer before spend."""
    config = bigquery.QueryJobConfig(maximum_bytes_billed=maximum_bytes_billed)
    if labels:
        config.labels = labels
    return config


def validate_backfill_window(
    start_date: date,
    end_date: date,
    *,
    max_days: int = DEFAULT_MAX_BACKFILL_DAYS,
    env: dict[str, str] | None = None,
) -> int:
    """Reject backfill windows beyond policy unless explicitly overridden.

    Returns the window size in days. The override variable must be exactly
    'true'; an unbounded backfill can never happen by accident.
    """
    env = env if env is not None else dict(os.environ)
    if end_date < start_date:
        raise CostGuardViolation(f"backfill window end {end_date} precedes start {start_date}")
    days = (end_date - start_date).days + 1
    if days > max_days and env.get(BACKFILL_OVERRIDE_VAR, "").lower() != "true":
        emit_event(
            "cost_guard_blocked",
            severity="ERROR",
            component="pipeline",
            check_name="backfill_window",
            observed_value=days,
            threshold=max_days,
            status="BLOCKED",
        )
        raise CostGuardViolation(
            f"backfill window of {days} days exceeds the {max_days}-day policy; "
            f"set {BACKFILL_OVERRIDE_VAR}=true only after a documented cost review"
        )
    return days


def require_full_refresh_approval(env: dict[str, str] | None = None) -> None:
    """Block dbt full refresh unless the approval variable is explicitly true."""
    env = env if env is not None else dict(os.environ)
    if env.get(FULL_REFRESH_APPROVAL_VAR, "").lower() != "true":
        emit_event(
            "cost_guard_blocked",
            severity="ERROR",
            component="pipeline",
            check_name="full_refresh_approval",
            status="BLOCKED",
        )
        raise CostGuardViolation(
            f"full refresh requires {FULL_REFRESH_APPROVAL_VAR}=true; "
            "incremental processing is the default and targeted repair is the "
            "first response to corruption (ADR-014)"
        )


def backfill_dates(start_date: date, days: int) -> list[Any]:
    """Enumerate the dates of a validated backfill window."""
    return [start_date + timedelta(days=offset) for offset in range(days)]
