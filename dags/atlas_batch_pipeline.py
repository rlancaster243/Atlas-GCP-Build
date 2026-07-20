"""Atlas batch pipeline DAG — Sprint 3 orchestration layer."""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG, task

# Composer parity: Airflow 3's DAG processor puts only the bundle root on
# sys.path. In Composer this DAG lives in <bucket>/dags/project_atlas/, so its
# own directory (for atlas_orchestration) and $ATLAS_ROOT/src (for atlas.*)
# must be added explicitly before package imports. Locally both are no-ops.
_DAG_DIR = Path(__file__).resolve().parent
ATLAS_ROOT = Path(os.environ.get("ATLAS_ROOT", Path(__file__).resolve().parents[1]))
for _extra in (str(_DAG_DIR), str(ATLAS_ROOT / "src")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from atlas_orchestration.callbacks import on_failure_callback, on_retry_callback
from atlas_orchestration.context import resolve_run_context_dict

DAG_ID = "atlas_batch_pipeline"
START_DATE = datetime(2026, 7, 1, tzinfo=UTC)
STEP_SCRIPT = ATLAS_ROOT / "scripts" / "run_atlas_step.sh"
CTX_TEMPLATE = "{{ ti.xcom_pull(task_ids='resolve_run_context') | tojson }}"


def _ensure_atlas_importable() -> None:
    """Make the atlas package importable inside task processes."""
    src = str(ATLAS_ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


def bash_step(task_id: str, step: str, *, retries: int = 0, retry_minutes: int = 2) -> BashOperator:
    """Create a BashOperator that dispatches one Atlas CLI step.

    The JSON run context is passed through the process environment rather than
    inline in the command, so shell quoting can never corrupt it.
    """
    return BashOperator(
        task_id=task_id,
        bash_command=f'"{STEP_SCRIPT}" {step} "$ATLAS_CTX"',
        env={
            "ATLAS_CTX": CTX_TEMPLATE,
            "ATLAS_TRY_NUMBER": "{{ ti.try_number }}",
        },
        append_env=True,
        retries=retries,
        retry_delay=timedelta(minutes=retry_minutes) if retries else None,
    )


@task(task_id="resolve_run_context", multiple_outputs=False)
def resolve_run_context(**context) -> dict:
    dag_run = context["dag_run"]
    ctx = resolve_run_context_dict(
        airflow_run_id=dag_run.run_id,
        dag_id=dag_run.dag_id,
        data_interval_end=context.get("data_interval_end"),
        conf=dag_run.conf or {},
    )
    # Python @tasks bypass the step runner's telemetry wrapper; record this
    # task's terminal event directly (best-effort, never fails the task).
    try:
        _ensure_atlas_importable()
        from atlas.ops.task_events import TaskEventRecord, record_task_event_safely

        record_task_event_safely(
            TaskEventRecord(
                pipeline_run_id=ctx["pipeline_run_id"],
                task_id="resolve_run_context",
                attempt_number=int(context["ti"].try_number or 1),
                event_type="SUCCESS",
                batch_id=ctx["batch_id"],
                airflow_run_id=ctx["airflow_run_id"],
                dag_id=ctx["dag_id"],
                status="SUCCESS",
                operator_type="PythonOperator",
            )
        )
    except Exception:  # noqa: BLE001, S110 - telemetry must never break the task
        pass
    return ctx


@task(task_id="write_run_summary", trigger_rule="all_done")
def write_run_summary(**context) -> dict:
    """Finalize the run: local JSON summary, BigQuery audit row, reconciliation.

    Runs with all_done and raises on FAILED/PARTIAL so this leaf cannot turn a
    failed DAG green.
    """
    _ensure_atlas_importable()
    from atlas.ops.audit import (
        PipelineRunRecord,
        collect_batch_metrics,
        finalize_pipeline_run,
        query_pipeline_run,
        write_local_run_summary,
    )
    from atlas.ops.finalizer import finalizer_should_fail, reconcile_run_summary

    ti = context["ti"]
    ctx = ti.xcom_pull(task_ids="resolve_run_context")
    if not ctx:
        raise RuntimeError("resolve_run_context produced no run context")

    # publish_success_marker only runs when the whole chain succeeded, so its
    # XCom presence is a reliable success signal under the all_done rule.
    marker = ti.xcom_pull(task_ids="publish_success_marker")
    status = "SUCCESS" if marker else "FAILED"

    completed_at = datetime.now(tz=UTC).isoformat()

    # Populate batch-scoped volumes for observability (best-effort; never fatal).
    metrics: dict = {}
    if status == "SUCCESS":
        try:
            metrics = collect_batch_metrics(ctx["batch_id"])
        except Exception:  # noqa: BLE001 - metrics are best-effort
            metrics = {}

    summary = {
        "pipeline_run_id": ctx["pipeline_run_id"],
        "batch_id": ctx["batch_id"],
        "processing_date": ctx["processing_date"],
        "status": status,
        "completed_at": completed_at,
        "airflow_run_id": ctx["airflow_run_id"],
        "dag_id": ctx["dag_id"],
        **metrics,
    }
    write_local_run_summary(ctx["pipeline_run_id"], summary)

    record = PipelineRunRecord(
        pipeline_run_id=ctx["pipeline_run_id"],
        batch_id=ctx["batch_id"],
        airflow_run_id=ctx["airflow_run_id"],
        dag_id=ctx["dag_id"],
        processing_date=ctx["processing_date"],
        started_at=completed_at,
        completed_at=completed_at,
        status=status,
        attempt_number=int(ti.try_number or 1),
        rows_loaded=metrics.get("rows_loaded"),
        rows_accepted=metrics.get("rows_accepted"),
        rows_rejected=metrics.get("rows_rejected"),
        fact_rows=metrics.get("fact_rows"),
    )
    audit_row = None
    try:
        finalize_pipeline_run(record)
        audit_row = query_pipeline_run(ctx["pipeline_run_id"])
    except Exception as exc:  # noqa: BLE001 - reconciliation records audit failures
        summary["audit_error"] = str(exc)

    summary["reconciliation"] = reconcile_run_summary(summary, audit_row)

    # Sprint 5: telemetry-completeness verification (best-effort; visible
    # degradation must never convert a successful data run into a failure).
    try:
        from atlas.ops.task_events import (
            TaskEventRecord,
            record_task_event_safely,
            telemetry_completeness,
        )

        completeness = telemetry_completeness(ctx["pipeline_run_id"])
        if status == "FAILED":
            # Tasks that never ran because an upstream failed get a durable
            # terminal event so the audit distinguishes "did not run" from
            # "telemetry lost".
            for missing_task in completeness["missing_terminal"]:
                record_task_event_safely(
                    TaskEventRecord(
                        pipeline_run_id=ctx["pipeline_run_id"],
                        task_id=missing_task,
                        attempt_number=1,
                        event_type="UPSTREAM_FAILED",
                        batch_id=ctx["batch_id"],
                        airflow_run_id=ctx["airflow_run_id"],
                        dag_id=ctx["dag_id"],
                        status="UPSTREAM_FAILED",
                        operator_type="finalizer",
                    )
                )
            completeness = telemetry_completeness(ctx["pipeline_run_id"])
        summary["task_telemetry"] = completeness
    except Exception as exc:  # noqa: BLE001 - telemetry check is best-effort
        summary["task_telemetry"] = {"complete": False, "error": str(exc)}

    write_local_run_summary(ctx["pipeline_run_id"], summary)

    if finalizer_should_fail(summary):
        raise RuntimeError(f"Pipeline run finalized with status={status}")
    return summary


with DAG(
    dag_id=DAG_ID,
    schedule="0 6 * * *",
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    # Deployments land paused: scheduled execution starts only after the smoke
    # batch succeeds and an operator unpauses deliberately (Sprint 4, Phase 12).
    is_paused_upon_creation=True,
    default_args={
        "owner": "atlas",
        "retries": 0,
        "on_failure_callback": on_failure_callback,
        "on_retry_callback": on_retry_callback,
    },
    tags=["atlas", "sprint3"],
) as dag:
    run_context = resolve_run_context()

    ensure_audit = bash_step("ensure_audit_resources", "ensure_audit_resources")
    start_audit = bash_step("start_run_audit", "start_run_audit")
    preflight = bash_step("preflight_environment", "preflight_environment")
    generate = bash_step("generate_events", "generate_events")
    upload = bash_step("upload_events", "upload_events", retries=2)
    load_raw = bash_step("load_bigquery_raw", "load_events", retries=2)
    validate_raw = bash_step("validate_raw_load", "validate_raw_load")
    seed = bash_step("dbt_seed", "dbt_seed")
    freshness = bash_step("dbt_source_freshness", "dbt_source_freshness", retries=1)
    build = bash_step("dbt_build", "dbt_build")
    validate_wh = bash_step("validate_warehouse", "validate_warehouse")
    publish = bash_step("publish_success_marker", "publish_success_marker")
    summary = write_run_summary()

    run_context >> ensure_audit >> start_audit >> preflight >> generate
    generate >> upload >> load_raw >> validate_raw >> seed >> freshness >> build
    build >> validate_wh >> publish >> summary
