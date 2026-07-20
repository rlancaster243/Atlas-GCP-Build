"""Task callbacks for retry and failure metadata capture.

Sprint 5: callbacks write RETRY/FAILED rows into ``atlas_ops.task_events``
best-effort. All atlas imports stay inside the functions so DAG parsing
performs no network calls and never depends on telemetry availability; a
telemetry failure can never fail the callback (and thus the task) itself.
"""

from __future__ import annotations

from typing import Any


def build_callback_context(context: dict[str, Any]) -> dict[str, Any]:
    """Extract minimal callback metadata from an Airflow task context."""
    task_instance = context.get("task_instance")
    dag_run = context.get("dag_run")
    return {
        "task_id": getattr(task_instance, "task_id", None),
        "try_number": getattr(task_instance, "try_number", None),
        "airflow_run_id": getattr(dag_run, "run_id", None),
        "dag_id": getattr(dag_run, "dag_id", None),
        "state": getattr(task_instance, "state", None),
        "start_date": getattr(task_instance, "start_date", None),
        "end_date": getattr(task_instance, "end_date", None),
    }


def derive_callback_timing(meta: dict[str, Any]) -> dict[str, Any]:
    """Derive timing evidence from Airflow task-instance timestamps.

    Sprint 6, Phase 1: FAILED/RETRY rows previously carried NULL timing. Use
    only reliable evidence — the task instance's own start/end dates. When the
    end date is not yet set at callback time, the callback wall clock bounds
    completion (confidence "partial"). Never invent timestamps: with no start
    date, everything stays NULL and confidence is recorded as "none".
    """
    from datetime import UTC, datetime

    start = meta.get("start_date")
    end = meta.get("end_date")
    if start is None:
        return {
            "started_at": None,
            "completed_at": None,
            "duration_ms": None,
            "timing_source": "airflow_task_instance",
            "timing_confidence": "none",
        }
    confidence = "exact"
    if end is None:
        end = datetime.now(tz=UTC)
        confidence = "partial"
    return {
        "started_at": start.isoformat(),
        "completed_at": end.isoformat(),
        "duration_ms": max(0, int((end - start).total_seconds() * 1000)),
        "timing_source": "airflow_task_instance",
        "timing_confidence": confidence,
    }


def _record_callback_event(context: dict[str, Any], event_type: str) -> None:
    meta = build_callback_context(context)
    try:
        from atlas.ops.task_events import TaskEventRecord, record_task_event_safely

        task_instance = context.get("task_instance")
        run_ctx: dict[str, Any] = {}
        try:
            run_ctx = task_instance.xcom_pull(task_ids="resolve_run_context") or {}
        except Exception:  # noqa: BLE001 - context may predate resolve_run_context
            run_ctx = {}
        timing = derive_callback_timing(meta)
        record_task_event_safely(
            TaskEventRecord(
                pipeline_run_id=run_ctx.get("pipeline_run_id", "unknown"),
                task_id=meta.get("task_id") or "unknown",
                attempt_number=max(1, int(meta.get("try_number") or 1)),
                event_type=event_type,
                batch_id=run_ctx.get("batch_id"),
                airflow_run_id=meta.get("airflow_run_id"),
                dag_id=meta.get("dag_id"),
                status=event_type,
                operator_type="callback",
                started_at=timing["started_at"],
                completed_at=timing["completed_at"],
                duration_ms=timing["duration_ms"],
                timing_source=timing["timing_source"],
                timing_confidence=timing["timing_confidence"],
            )
        )
    except Exception:  # noqa: BLE001, S110 - callbacks must never raise
        pass


def on_retry_callback(context: dict[str, Any]) -> None:
    """Record a RETRY task event (best-effort, no import-time network)."""
    _record_callback_event(context, "RETRY")


def on_failure_callback(context: dict[str, Any]) -> None:
    """Record a FAILED task event (best-effort, no import-time network)."""
    _record_callback_event(context, "FAILED")
