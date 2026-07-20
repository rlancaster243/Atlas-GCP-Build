"""Parse-time-safe run context resolution for Atlas Airflow DAGs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from atlas.batch.context import resolve_batch_context


def resolve_processing_date(
    data_interval_end: datetime | None,
    manual_processing_date: str | None = None,
) -> str:
    """Derive the processing date from the UTC data interval end."""
    if manual_processing_date:
        datetime.strptime(manual_processing_date, "%Y-%m-%d")
        return manual_processing_date
    if data_interval_end is None:
        return datetime.now(tz=UTC).date().isoformat()
    if data_interval_end.tzinfo is None:
        data_interval_end = data_interval_end.replace(tzinfo=UTC)
    return data_interval_end.astimezone(UTC).date().isoformat()


def resolve_run_context_dict(
    *,
    airflow_run_id: str,
    dag_id: str,
    data_interval_end: datetime | None = None,
    conf: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a validated run-context dictionary for XCom and command builders."""
    conf = conf or {}
    processing_date = resolve_processing_date(
        data_interval_end,
        manual_processing_date=conf.get("processing_date"),
    )
    context = resolve_batch_context(
        processing_date=processing_date,
        batch_id=conf.get("batch_id"),
        pipeline_run_id=conf.get("pipeline_run_id"),
        seed=conf.get("seed"),
        airflow_run_id=airflow_run_id,
    )
    manual = conf.get("processing_date")
    scheduled = resolve_processing_date(data_interval_end)
    backfill_mode = manual is not None and manual != scheduled
    if backfill_mode:
        # Sprint 6 cost guard (S6-COST-002): a backfill reaching further back
        # than policy allows must be an explicit, reviewed decision — never an
        # accident of a mistyped date. Import stays inside the branch so DAG
        # parsing never touches the guard's BigQuery dependency.
        from datetime import date as _date

        from atlas.observability.cost_guards import validate_backfill_window

        manual_date = _date.fromisoformat(str(manual))
        scheduled_date = _date.fromisoformat(scheduled)
        window = sorted([manual_date, scheduled_date])
        validate_backfill_window(window[0], window[1])
    return {
        "processing_date": context.processing_date,
        "batch_id": context.batch_id,
        "pipeline_run_id": context.pipeline_run_id,
        "seed": context.seed,
        "local_file_path": str(context.local_file_path),
        "manifest_path": str(context.manifest_path),
        "airflow_run_id": airflow_run_id,
        "dag_id": dag_id,
        "upload_once": bool(conf.get("upload_once")),
        "dbt_test_failure": bool(conf.get("dbt_test_failure")),
        "backfill_mode": backfill_mode,
    }
