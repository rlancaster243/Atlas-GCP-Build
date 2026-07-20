"""Execute one Atlas orchestration step from JSON context."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _ctx() -> dict[str, Any]:
    if len(sys.argv) < 3:
        raise SystemExit("Usage: atlas_step_runner.py <step> <json-context>")
    try:
        return json.loads(sys.argv[2])
    except json.JSONDecodeError as exc:
        raise SystemExit(f"atlas_step_runner: invalid JSON context for step {sys.argv[1]!r}: {exc}") from exc


def _run(cmd: list[str], *, cwd: Path | None = None) -> None:
    subprocess.check_call(cmd, cwd=cwd)


def _attempt_number() -> int:
    for var in ("ATLAS_TRY_NUMBER", "AIRFLOW_CTX_TRY_NUMBER"):
        raw = os.environ.get(var)
        if raw and raw.isdigit():
            return max(1, int(raw))
    return 1


def _record_step_event(step: str, ctx: dict[str, Any], event_type: str, **extra: Any) -> None:
    """Best-effort task telemetry (Sprint 5, Phase 3). Never raises."""
    try:
        from atlas.observability.logging import emit_event
        from atlas.ops.task_events import TaskEventRecord, record_task_event_safely

        record = TaskEventRecord(
            pipeline_run_id=ctx.get("pipeline_run_id", "unknown"),
            task_id=os.environ.get("AIRFLOW_CTX_TASK_ID") or step,
            attempt_number=_attempt_number(),
            event_type=event_type,
            batch_id=ctx.get("batch_id"),
            airflow_run_id=ctx.get("airflow_run_id"),
            dag_id=ctx.get("dag_id"),
            status=extra.get("status"),
            started_at=extra.get("started_at"),
            completed_at=extra.get("completed_at"),
            duration_ms=extra.get("duration_ms"),
            operator_type="BashOperator",
            environment=os.environ.get("ATLAS_ENVIRONMENT", "atlas-dev"),
            git_sha=os.environ.get("ATLAS_DEPLOYED_GIT_SHA"),
            error_type=extra.get("error_type"),
            error_message=extra.get("error_message"),
            # Sprint 6, Phase 1: runner-measured timing is exact by construction.
            timing_source="step_runner_clock" if extra.get("started_at") else None,
            timing_confidence="exact" if extra.get("started_at") else None,
        )
        record_task_event_safely(record)
        emit_event(
            f"task_{event_type.lower()}",
            severity="ERROR" if event_type == "FAILED" else "INFO",
            component="step_runner",
            pipeline_run_id=ctx.get("pipeline_run_id"),
            batch_id=ctx.get("batch_id"),
            airflow_run_id=ctx.get("airflow_run_id"),
            dag_id=ctx.get("dag_id"),
            task_id=os.environ.get("AIRFLOW_CTX_TASK_ID") or step,
            attempt_number=_attempt_number(),
            duration_ms=extra.get("duration_ms"),
            error_type=extra.get("error_type"),
            error_message=extra.get("error_message"),
        )
    except Exception:  # noqa: BLE001, S110 - telemetry must never break the step
        pass


def main() -> int:
    """Telemetry wrapper: STARTED/terminal task events around the dispatch.

    Telemetry failures never change the step's exit code; the terminal event
    mirrors the dispatch outcome (0 -> SUCCESS/SKIPPED, else FAILED).
    """
    step = sys.argv[1]
    ctx = _ctx()
    started_at = datetime.now(tz=UTC).isoformat()
    start = time.perf_counter()
    _record_step_event(step, ctx, "STARTED", started_at=started_at)
    try:
        code = _dispatch(step, ctx)
    except subprocess.CalledProcessError as exc:
        _record_step_event(
            step,
            ctx,
            "FAILED",
            status="FAILED",
            started_at=started_at,
            completed_at=datetime.now(tz=UTC).isoformat(),
            duration_ms=int((time.perf_counter() - start) * 1000),
            error_type="CalledProcessError",
            error_message=f"command exited {exc.returncode}",
        )
        raise
    except Exception as exc:
        _record_step_event(
            step,
            ctx,
            "FAILED",
            status="FAILED",
            started_at=started_at,
            completed_at=datetime.now(tz=UTC).isoformat(),
            duration_ms=int((time.perf_counter() - start) * 1000),
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        raise
    skipped = step == "dbt_source_freshness" and bool(ctx.get("backfill_mode"))
    terminal = "SKIPPED" if (code == 0 and skipped) else ("SUCCESS" if code == 0 else "FAILED")
    _record_step_event(
        step,
        ctx,
        terminal,
        status=terminal,
        started_at=started_at,
        completed_at=datetime.now(tz=UTC).isoformat(),
        duration_ms=int((time.perf_counter() - start) * 1000),
        error_message=None if code == 0 else f"step returned exit code {code}",
    )
    return code


def _dispatch(step: str, ctx: dict[str, Any]) -> int:
    root = Path(__import__("os").environ.get("ATLAS_ROOT", Path(__file__).resolve().parents[1]))
    dbt_dir = Path(__import__("os").environ.get("DBT_PROJECT_DIR", root / "dbt" / "atlas_dbt"))
    profiles_dir = __import__("os").environ.get("DBT_PROFILES_DIR", str(Path.home() / ".dbt"))

    if step == "ensure_audit_resources":
        from atlas.ops.resources import ensure_audit_resources

        ensure_audit_resources()
        print(json.dumps({"status": "PASS"}))
        return 0

    if step == "start_run_audit":
        from atlas.ops.audit import start_pipeline_run

        record = start_pipeline_run(
            pipeline_run_id=ctx["pipeline_run_id"],
            batch_id=ctx["batch_id"],
            airflow_run_id=ctx["airflow_run_id"],
            dag_id=ctx["dag_id"],
            processing_date=ctx["processing_date"],
        )
        print(json.dumps({"status": record.status, "pipeline_run_id": record.pipeline_run_id}))
        return 0

    if step == "preflight_environment":
        from atlas.ops.preflight import preflight_environment

        result = preflight_environment()
        print(json.dumps({"status": result.status, "checks": result.checks}))
        return 0 if result.status == "PASS" else 1

    if step == "generate_events":
        cmd = [
            sys.executable,
            str(root / "scripts" / "generate_events.py"),
            "--processing-date",
            ctx["processing_date"],
            "--batch-id",
            ctx["batch_id"],
            "--pipeline-run-id",
            ctx["pipeline_run_id"],
        ]
        if ctx.get("seed") is not None:
            cmd.extend(["--seed", str(ctx["seed"])])
        _run(cmd)
        return 0

    if step == "upload_events":
        gen = subprocess.check_output(
            [
                sys.executable,
                str(root / "scripts" / "generate_events.py"),
                "--processing-date",
                ctx["processing_date"],
                "--batch-id",
                ctx["batch_id"],
                "--pipeline-run-id",
                ctx["pipeline_run_id"],
            ],
            text=True,
        )
        checksum = json.loads(gen).get("checksum_sha256")
        cmd = [
            sys.executable,
            str(root / "scripts" / "upload_events.py"),
            "--local-path",
            ctx["local_file_path"],
            "--event-date",
            ctx["processing_date"],
            "--run-id",
            ctx["pipeline_run_id"],
            "--batch-id",
            ctx["batch_id"],
        ]
        if checksum:
            cmd.extend(["--expected-checksum", checksum])
        try_number = int(
            __import__("os").environ.get(
                "ATLAS_TRY_NUMBER",
                __import__("os").environ.get("AIRFLOW_CTX_TRY_NUMBER", "1"),
            )
        )
        if ctx.get("upload_once") and try_number == 1:
            cmd.append("--fail-once")
        _run(cmd)
        return 0

    if step == "load_events":
        bucket = __import__("os").environ.get("ATLAS_GCS_BUCKET", "atlas-raw-events-example-gcp-project")
        object_path = f"raw/event_date={ctx['processing_date']}/batch_id={ctx['batch_id']}/events.jsonl"
        _run(
            [
                sys.executable,
                str(root / "scripts" / "load_events.py"),
                "--gcs-uri",
                f"gs://{bucket}/{object_path}",
                "--run-id",
                ctx["pipeline_run_id"],
                "--batch-id",
                ctx["batch_id"],
                "--processing-date",
                ctx["processing_date"],
                "--expected-row-count",
                "50000",
            ]
        )
        return 0

    if step == "validate_raw_load":
        _run(
            [
                sys.executable,
                str(root / "scripts" / "validate_events.py"),
                "--batch-id",
                ctx["batch_id"],
                "--event-date",
                ctx["processing_date"],
                "--processing-date",
                ctx["processing_date"],
                "--mode",
                "airflow",
            ]
        )
        return 0

    if step == "dbt_seed":
        _run(["dbt", "seed", "--profiles-dir", profiles_dir], cwd=dbt_dir)
        return 0

    if step == "dbt_source_freshness":
        if ctx.get("backfill_mode"):
            print(json.dumps({"status": "SKIPPED", "reason": "backfill_mode"}))
            return 0
        _run(["dbt", "source", "freshness", "--profiles-dir", profiles_dir], cwd=dbt_dir)
        return 0

    if step == "dbt_build":
        vars_payload: dict[str, Any] = {"validated_batch_id": ctx["batch_id"]}
        if ctx.get("dbt_test_failure"):
            vars_payload["inject_failure"] = True
        cmd = ["dbt", "build", "--profiles-dir", profiles_dir, "--vars", json.dumps(vars_payload)]
        if ctx.get("full_refresh"):
            # Sprint 6 cost guard (S6-COST-003): full refresh rebuilds every
            # incremental target and is never the default recovery response.
            from atlas.observability.cost_guards import require_full_refresh_approval

            require_full_refresh_approval()
            cmd.append("--full-refresh")
        _run(cmd, cwd=dbt_dir)
        return 0

    if step == "validate_warehouse":
        from atlas.observability.checks import persist_warehouse_report
        from atlas.validation.warehouse import validate_warehouse

        report = validate_warehouse(ctx["batch_id"], ctx["processing_date"])
        # Durable quality evidence (Sprint 5, Phase 4); persistence problems
        # surface as structured telemetry, never as a changed validation verdict.
        # External re-validation (e.g. validate_atlas_deployment.sh) passes no
        # pipeline_run_id; skip persistence then instead of inventing a run.
        if ctx.get("pipeline_run_id"):
            persist_warehouse_report(
                report,
                ctx["pipeline_run_id"],
                git_sha=os.environ.get("ATLAS_DEPLOYED_GIT_SHA"),
            )
        print(json.dumps(report.to_dict(), indent=2, default=str))
        return 0 if report.overall_status == "PASS" else 1

    if step == "publish_success_marker":
        marker_dir = root / "data" / "runs" / ctx["batch_id"]
        marker_dir.mkdir(parents=True, exist_ok=True)
        (marker_dir / "success.marker").write_text(datetime.now(tz=UTC).isoformat(), encoding="utf-8")
        print(json.dumps({"status": "PASS", "batch_id": ctx["batch_id"]}))
        return 0

    if step == "write_run_summary":
        from atlas.ops.audit import (
            PipelineRunRecord,
            finalize_pipeline_run,
            query_pipeline_run,
            write_local_run_summary,
        )
        from atlas.ops.finalizer import finalizer_should_fail, reconcile_run_summary

        dag_state = __import__("os").environ.get("AIRFLOW_CTX_DAG_RUN_STATE", "success")
        status = "SUCCESS" if dag_state.lower() == "success" else "FAILED"
        summary = {
            "pipeline_run_id": ctx["pipeline_run_id"],
            "batch_id": ctx["batch_id"],
            "processing_date": ctx["processing_date"],
            "status": status,
            "completed_at": datetime.now(tz=UTC).isoformat(),
        }
        write_local_run_summary(ctx["pipeline_run_id"], summary)
        record = PipelineRunRecord(
            pipeline_run_id=ctx["pipeline_run_id"],
            batch_id=ctx["batch_id"],
            airflow_run_id=ctx["airflow_run_id"],
            dag_id=ctx["dag_id"],
            processing_date=ctx["processing_date"],
            started_at=summary["completed_at"],
            completed_at=summary["completed_at"],
            status=status,
            attempt_number=int(__import__("os").environ.get("AIRFLOW_CTX_TRY_NUMBER", "1")),
        )
        try:
            finalize_pipeline_run(record)
            audit_row = query_pipeline_run(ctx["pipeline_run_id"])
        except Exception as exc:  # noqa: BLE001
            audit_row = None
            summary["audit_error"] = str(exc)
        summary["reconciliation"] = reconcile_run_summary(summary, audit_row)
        write_local_run_summary(ctx["pipeline_run_id"], summary)
        print(json.dumps(summary, indent=2))
        return 1 if finalizer_should_fail(summary) else 0

    raise SystemExit(f"Unknown step: {step}")


if __name__ == "__main__":
    raise SystemExit(main())
