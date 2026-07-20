"""Atlas observability monitor engine (Sprint 5, Phase 8).

Evaluates system health independently of the business pipeline. Read-only
against all canonical data; its only writes are ``atlas_ops.monitor_evaluations``
rows and Cloud Monitoring metric points. Every check:

- uses bounded time windows from ``config/observability.yaml``,
- handles NO_DATA explicitly (and DISABLED when monitoring_enabled=false,
  e.g. before intentional Composer teardown),
- emits one structured log event and one ``atlas/monitor/check_status``
  metric point (0=PASS 1=WARN 2=FAIL -1=NO_DATA -2=DISABLED),
- persists one durable evaluation row.

Composer platform health is deliberately NOT re-implemented here: native
``composer.googleapis.com/environment/healthy`` metrics feed that alert
policy directly (ADR-011: never re-create native platform metrics).
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from atlas.config.settings import AtlasSettings, load_settings
from atlas.observability.logging import emit_event
from atlas.observability.metrics import MONITOR_STATUS_VALUES, publish_gauge_safely
from atlas.ops.quality_results import MonitorEvaluationRecord, upsert_monitor_evaluation

_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "observability.yaml"

CHECK_NAMES = (
    "latest_run_state",
    "freshness",
    "missing_scheduled_run",
    "telemetry_completeness",
    "reconciliation",
    "volume_deviation",
    "rejection_rate",
    "schema_drift",
    "deployment_failure",
    "rollback_failure",
    "cost_anomaly",
)


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load observability.yaml and apply drill overrides (file + env)."""
    config = yaml.safe_load((path or _CONFIG_PATH).read_text(encoding="utf-8"))
    overrides = dict(config.get("drill_overrides") or {})
    env_overrides = os.environ.get("ATLAS_OBSERVABILITY_OVERRIDES_JSON")
    if env_overrides:
        overrides.update(json.loads(env_overrides))
    for section, values in overrides.items():
        if isinstance(values, dict) and isinstance(config.get(section), dict):
            config[section].update(values)
        else:
            config[section] = values
    return config


@dataclass
class CheckResult:
    """Outcome of one monitor check before persistence."""

    check_name: str
    status: str  # PASS | WARN | FAIL | NO_DATA | DISABLED
    severity: str = "INFO"
    observed_value: float | None = None
    threshold: float | None = None
    details: dict[str, Any] | None = None
    extra_metrics: list[tuple[str, float, dict[str, str]]] | None = None


def _rows(client: Any, sql: str) -> list[dict[str, Any]]:
    return [dict(row) for row in client.query(sql).result()]


def check_latest_run_state(client: Any, config: dict[str, Any], project_id: str) -> CheckResult:
    window = int(config.get("telemetry", {}).get("window_hours", 48))
    rows = _rows(
        client,
        f"""
        SELECT status, pipeline_run_id, started_at,
               TIMESTAMP_DIFF(COALESCE(completed_at, CURRENT_TIMESTAMP()), started_at, SECOND) AS duration_s
        FROM `{project_id}.atlas_ops.pipeline_runs`
        WHERE started_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {window} HOUR)
        ORDER BY started_at DESC LIMIT 1
        """,
    )
    if not rows:
        return CheckResult("latest_run_state", "NO_DATA", details={"window_hours": window})
    row = rows[0]
    failed = row["status"] == "FAILED"
    return CheckResult(
        "latest_run_state",
        "FAIL" if failed else ("WARN" if row["status"] == "RUNNING" else "PASS"),
        severity="CRITICAL" if failed else "INFO",
        observed_value=float(row["duration_s"] or 0),
        details={"pipeline_run_id": row["pipeline_run_id"], "status": row["status"]},
        extra_metrics=[
            (
                "custom.googleapis.com/atlas/pipeline/run_duration_seconds",
                float(row["duration_s"] or 0),
                {"dag_id": "atlas_batch_pipeline", "status": "FAILED" if failed else "SUCCESS"},
            )
        ],
    )


def check_freshness(client: Any, config: dict[str, Any], project_id: str) -> CheckResult:
    warn = float(config["freshness"]["warn_seconds"])
    fail = float(config["freshness"]["fail_seconds"])
    rows = _rows(
        client,
        f"""
        SELECT TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MAX(completed_at), SECOND) AS age_s
        FROM `{project_id}.atlas_ops.pipeline_runs`
        WHERE status = 'SUCCESS'
          AND completed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
        """,
    )
    age = rows[0]["age_s"] if rows and rows[0]["age_s"] is not None else None
    if age is None:
        return CheckResult("freshness", "NO_DATA", details={"reason": "no successful run in 30d"})
    status = "FAIL" if age >= fail else ("WARN" if age >= warn else "PASS")
    return CheckResult(
        "freshness",
        status,
        severity="CRITICAL" if status == "FAIL" else ("WARNING" if status == "WARN" else "INFO"),
        observed_value=float(age),
        threshold=fail if status == "FAIL" else warn,
        extra_metrics=[
            (
                "custom.googleapis.com/atlas/pipeline/last_success_age_seconds",
                float(age),
                {"dag_id": "atlas_batch_pipeline"},
            )
        ],
    )


def check_missing_scheduled_run(client: Any, config: dict[str, Any], project_id: str) -> CheckResult:
    grace = int(config["expected_schedule"]["grace_seconds"])
    expected_interval = 86400 + grace  # daily schedule + grace
    rows = _rows(
        client,
        f"""
        SELECT TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MAX(started_at), SECOND) AS since_any_s
        FROM `{project_id}.atlas_ops.pipeline_runs`
        WHERE started_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
        """,
    )
    since = rows[0]["since_any_s"] if rows and rows[0]["since_any_s"] is not None else None
    if since is None:
        # No runs at all in 30d: the DAG is deliberately paused between
        # acceptance windows (default state), which is disabled runtime, not
        # staleness. monitoring_enabled=false turns the whole monitor off.
        return CheckResult(
            "missing_scheduled_run", "NO_DATA", details={"reason": "no runs in 30d (DAG paused)"}
        )
    status = "FAIL" if since > expected_interval else "PASS"
    return CheckResult(
        "missing_scheduled_run",
        status,
        severity="WARNING" if status == "FAIL" else "INFO",
        observed_value=float(since),
        threshold=float(expected_interval),
    )


def check_telemetry_completeness(client: Any, config: dict[str, Any], project_id: str) -> CheckResult:
    window = int(config.get("telemetry", {}).get("window_hours", 48))
    rows = _rows(
        client,
        f"""
        WITH latest AS (
          -- Only terminal runs: an in-progress run legitimately has missing
          -- terminal task events, so evaluating it produces false positives
          -- (defect found live during Sprint 5 acceptance).
          SELECT pipeline_run_id FROM `{project_id}.atlas_ops.pipeline_runs`
          WHERE started_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {window} HOUR)
            AND status IN ('SUCCESS', 'FAILED')
          ORDER BY started_at DESC LIMIT 1
        )
        SELECT l.pipeline_run_id,
               (SELECT COUNT(DISTINCT task_id) FROM `{project_id}.atlas_ops.task_events` te
                WHERE te.pipeline_run_id = l.pipeline_run_id
                  AND te.event_type IN ('SUCCESS','FAILED','SKIPPED','UPSTREAM_FAILED')) AS terminal_tasks
        FROM latest l
        """,
    )
    if not rows:
        return CheckResult("telemetry_completeness", "NO_DATA", details={"window_hours": window})
    from atlas.ops.task_events import EXPECTED_TERMINAL_TASKS

    expected = len(EXPECTED_TERMINAL_TASKS)
    missing = max(0, expected - int(rows[0]["terminal_tasks"]))
    return CheckResult(
        "telemetry_completeness",
        "FAIL" if missing else "PASS",
        severity="WARNING" if missing else "INFO",
        observed_value=float(missing),
        threshold=0.0,
        details={"pipeline_run_id": rows[0]["pipeline_run_id"], "expected_tasks": expected},
        extra_metrics=[
            (
                "custom.googleapis.com/atlas/pipeline/telemetry_incomplete_count",
                float(missing),
                {"dag_id": "atlas_batch_pipeline"},
            )
        ],
    )


def check_reconciliation(client: Any, config: dict[str, Any], project_id: str) -> CheckResult:
    window = int(config.get("reconciliation", {}).get("window_hours", 48))
    rows = _rows(
        client,
        f"""
        WITH latest AS (
          SELECT pipeline_run_id FROM `{project_id}.atlas_ops.quality_results`
          WHERE evaluated_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {window} HOUR)
          ORDER BY evaluated_at DESC LIMIT 1
        )
        SELECT l.pipeline_run_id,
               (SELECT COUNTIF(status = 'FAIL') FROM `{project_id}.atlas_ops.quality_results` qr
                WHERE qr.pipeline_run_id = l.pipeline_run_id) AS failed_checks
        FROM latest l
        """,
    )
    if not rows:
        return CheckResult("reconciliation", "NO_DATA", details={"window_hours": window})
    failed = int(rows[0]["failed_checks"])
    return CheckResult(
        "reconciliation",
        "FAIL" if failed else "PASS",
        severity="CRITICAL" if failed else "INFO",
        observed_value=float(failed),
        threshold=0.0,
        details={"pipeline_run_id": rows[0]["pipeline_run_id"]},
        extra_metrics=[("custom.googleapis.com/atlas/data/reconciliation_failure_count", float(failed), {})],
    )


def check_volume_deviation(client: Any, config: dict[str, Any], project_id: str) -> CheckResult:
    cfg = config["volume"]
    n = int(cfg["baseline_window_runs"])
    rows = _rows(
        client,
        f"""
        WITH recent AS (
          SELECT rows_loaded, started_at
          FROM `{project_id}.atlas_ops.pipeline_runs`
          WHERE status = 'SUCCESS' AND rows_loaded IS NOT NULL
            AND started_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
          ORDER BY started_at DESC LIMIT {n + 1}
        )
        SELECT
          (SELECT rows_loaded FROM recent ORDER BY started_at DESC LIMIT 1) AS latest_rows,
          (SELECT APPROX_QUANTILES(rows_loaded, 2)[OFFSET(1)]
             FROM (SELECT rows_loaded FROM recent ORDER BY started_at DESC LIMIT {n} OFFSET 1)
          ) AS baseline_rows
        """,
    )
    latest = rows[0]["latest_rows"] if rows else None
    baseline = rows[0]["baseline_rows"] if rows else None
    if latest is None:
        return CheckResult("volume_deviation", "NO_DATA", details={"reason": "no successful runs"})
    if baseline is None or baseline < int(cfg["min_baseline_rows"]):
        return CheckResult(
            "volume_deviation",
            "NO_DATA",
            observed_value=float(latest),
            details={"reason": "insufficient baseline", "baseline": baseline},
            extra_metrics=[("custom.googleapis.com/atlas/data/raw_row_count", float(latest), {})],
        )
    ratio = float(latest) / float(baseline)
    deviation = abs(1.0 - ratio)
    warn, fail = float(cfg["warn_deviation"]), float(cfg["fail_deviation"])
    status = "FAIL" if deviation >= fail else ("WARN" if deviation >= warn else "PASS")
    return CheckResult(
        "volume_deviation",
        status,
        severity="CRITICAL" if status == "FAIL" else ("WARNING" if status == "WARN" else "INFO"),
        observed_value=ratio,
        threshold=fail if status == "FAIL" else warn,
        details={"latest_rows": latest, "baseline_rows": baseline},
        extra_metrics=[
            ("custom.googleapis.com/atlas/data/raw_row_count", float(latest), {}),
            ("custom.googleapis.com/atlas/data/volume_deviation_ratio", ratio, {}),
        ],
    )


def check_rejection_rate(client: Any, config: dict[str, Any], project_id: str) -> CheckResult:
    cfg = config["rejection_rate"]
    rows = _rows(
        client,
        f"""
        SELECT rows_loaded, rows_accepted, rows_rejected
        FROM `{project_id}.atlas_ops.pipeline_runs`
        WHERE status = 'SUCCESS' AND rows_loaded IS NOT NULL AND rows_rejected IS NOT NULL
          AND started_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
        ORDER BY started_at DESC LIMIT 1
        """,
    )
    if not rows or not rows[0]["rows_loaded"]:
        return CheckResult("rejection_rate", "NO_DATA", details={"reason": "no volume data"})
    row = rows[0]
    rate = float(row["rows_rejected"]) / float(row["rows_loaded"])
    warn, fail = float(cfg["warn"]), float(cfg["fail"])
    status = "FAIL" if rate >= fail else ("WARN" if rate >= warn else "PASS")
    return CheckResult(
        "rejection_rate",
        status,
        severity="CRITICAL" if status == "FAIL" else ("WARNING" if status == "WARN" else "INFO"),
        observed_value=rate,
        threshold=fail if status == "FAIL" else warn,
        extra_metrics=[
            ("custom.googleapis.com/atlas/data/rejection_rate", rate, {}),
            ("custom.googleapis.com/atlas/data/accepted_row_count", float(row["rows_accepted"] or 0), {}),
            ("custom.googleapis.com/atlas/data/rejected_row_count", float(row["rows_rejected"]), {}),
        ],
    )


def check_schema_drift(client: Any, config: dict[str, Any], project_id: str) -> CheckResult:
    from atlas.observability.schema_drift import detect_drift, summarize

    findings = detect_drift(
        client,
        project_id,
        allowed_new_fields=config.get("schema", {}).get("allowed_new_fields") or [],
    )
    counts = summarize(findings)
    if counts["BREAKING"]:
        status, severity = "FAIL", "CRITICAL"
    elif counts["WARNING"]:
        status, severity = "WARN", "WARNING"
    else:
        status, severity = "PASS", "INFO"
    sample = [f.__dict__ for f in findings if f.classification != "ALLOWED"][:10]
    return CheckResult(
        "schema_drift",
        status,
        severity=severity,
        observed_value=float(counts["BREAKING"] + counts["WARNING"]),
        threshold=0.0,
        details={"counts": counts, "sample": sample},
        extra_metrics=[
            (
                "custom.googleapis.com/atlas/data/schema_drift_count",
                float(count),
                {"severity": label},
            )
            for label, count in (
                ("CRITICAL", counts["BREAKING"]),
                ("WARNING", counts["WARNING"]),
                ("INFO", counts["ALLOWED"]),
            )
        ],
    )


def _latest_deployment(
    client: Any, project_id: str, window_hours: int, deployment_type: str | None
) -> dict[str, Any] | None:
    type_clause = f"AND deployment_type = '{deployment_type}'" if deployment_type else ""
    rows = _rows(
        client,
        f"""
        SELECT deployment_id, status, deployment_type,
               TIMESTAMP_DIFF(COALESCE(completed_at, CURRENT_TIMESTAMP()), started_at, SECOND) AS duration_s
        FROM `{project_id}.atlas_ops.deployments`
        WHERE started_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {window_hours} HOUR)
          {type_clause}
        ORDER BY started_at DESC LIMIT 1
        """,
    )
    return rows[0] if rows else None


def check_deployment_failure(client: Any, config: dict[str, Any], project_id: str) -> CheckResult:
    window = int(config.get("deployment", {}).get("window_hours", 168))
    row = _latest_deployment(client, project_id, window, None)
    if row is None:
        return CheckResult("deployment_failure", "NO_DATA", details={"window_hours": window})
    failed = row["status"] in {"FAILED", "ROLLBACK_FAILED"}
    status_label = "FAILED" if failed else ("ROLLED_BACK" if row["status"] == "ROLLED_BACK" else "SUCCESS")
    return CheckResult(
        "deployment_failure",
        "FAIL" if failed else "PASS",
        severity="CRITICAL" if failed else "INFO",
        observed_value=1.0 if failed else 0.0,
        threshold=0.0,
        details={"deployment_id": row["deployment_id"], "status": row["status"]},
        extra_metrics=[
            ("custom.googleapis.com/atlas/deployment/latest_failed", 1.0 if failed else 0.0, {}),
            (
                "custom.googleapis.com/atlas/deployment/duration_seconds",
                float(row["duration_s"] or 0),
                {"status": status_label},
            ),
        ],
    )


def check_rollback_failure(client: Any, config: dict[str, Any], project_id: str) -> CheckResult:
    window = int(config.get("deployment", {}).get("window_hours", 168))
    row = _latest_deployment(client, project_id, window, "rollback")
    if row is None:
        return CheckResult("rollback_failure", "NO_DATA", details={"window_hours": window})
    failed = row["status"] == "ROLLBACK_FAILED"
    return CheckResult(
        "rollback_failure",
        "FAIL" if failed else "PASS",
        severity="CRITICAL" if failed else "INFO",
        observed_value=1.0 if failed else 0.0,
        threshold=0.0,
        details={"deployment_id": row["deployment_id"], "status": row["status"]},
    )


def check_cost_anomaly(client: Any, config: dict[str, Any], project_id: str) -> CheckResult:
    cfg = config["cost"]
    window_h = int(cfg["window_hours"])
    baseline_d = int(cfg["baseline_window_days"])
    rows = _rows(
        client,
        f"""
        SELECT
          SUM(IF(creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {window_h} HOUR),
                 total_bytes_billed, 0)) AS window_bytes,
          SUM(IF(creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {window_h} HOUR),
                 1, 0)) AS window_jobs,
          SAFE_DIVIDE(
            SUM(IF(creation_time < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {window_h} HOUR),
                   total_bytes_billed, 0)),
            {baseline_d}) AS baseline_daily_bytes
        FROM `{project_id}.region-us.INFORMATION_SCHEMA.JOBS`
        WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {baseline_d + 1} DAY)
          AND ('application', 'atlas') IN (SELECT (key, value) FROM UNNEST(labels))
          AND statement_type != 'SCRIPT'
        """,
    )
    if not rows:
        return CheckResult("cost_anomaly", "NO_DATA")
    window_bytes = float(rows[0]["window_bytes"] or 0)
    window_jobs = float(rows[0]["window_jobs"] or 0)
    baseline = float(rows[0]["baseline_daily_bytes"] or 0)
    metrics: list[tuple[str, float, dict[str, str]]] = [
        ("custom.googleapis.com/atlas/cost/bigquery_bytes_billed", window_bytes, {}),
        ("custom.googleapis.com/atlas/cost/bigquery_job_count", window_jobs, {}),
    ]
    if window_bytes < float(cfg["min_bytes_billed"]):
        return CheckResult(
            "cost_anomaly",
            "PASS",
            observed_value=window_bytes,
            details={"reason": "below absolute floor", "baseline_daily_bytes": baseline},
            extra_metrics=metrics,
        )
    if baseline <= 0:
        return CheckResult(
            "cost_anomaly",
            "NO_DATA",
            observed_value=window_bytes,
            details={"reason": "no baseline"},
            extra_metrics=metrics,
        )
    ratio = window_bytes / baseline
    warn, fail = float(cfg["warn_ratio"]), float(cfg["fail_ratio"])
    status = "FAIL" if ratio >= fail else ("WARN" if ratio >= warn else "PASS")
    return CheckResult(
        "cost_anomaly",
        status,
        severity="CRITICAL" if status == "FAIL" else ("WARNING" if status == "WARN" else "INFO"),
        observed_value=ratio,
        threshold=fail if status == "FAIL" else warn,
        details={"window_bytes": window_bytes, "baseline_daily_bytes": baseline},
        extra_metrics=metrics,
    )


CHECKS = {
    "latest_run_state": check_latest_run_state,
    "freshness": check_freshness,
    "missing_scheduled_run": check_missing_scheduled_run,
    "telemetry_completeness": check_telemetry_completeness,
    "reconciliation": check_reconciliation,
    "volume_deviation": check_volume_deviation,
    "rejection_rate": check_rejection_rate,
    "schema_drift": check_schema_drift,
    "deployment_failure": check_deployment_failure,
    "rollback_failure": check_rollback_failure,
    "cost_anomaly": check_cost_anomaly,
}


def run_monitor(
    *,
    settings: AtlasSettings | None = None,
    client: Any | None = None,
    config: dict[str, Any] | None = None,
    window_start: str | None = None,
    window_end: str | None = None,
    persist: bool = True,
    publish: bool = True,
) -> list[CheckResult]:
    """Run every monitor check; persist evaluations and publish metrics."""
    settings = settings or load_settings()
    config = config or load_config()
    environment = config.get("environment", "atlas-dev")
    mode = config.get("runtime_mode", "normal")
    enabled = bool(config.get("monitoring_enabled", True))
    now = datetime.now(tz=UTC).isoformat()
    window_end = window_end or now

    if client is None:
        from atlas.observability.cost import labeled_bigquery_client

        client = labeled_bigquery_client(settings.gcp.project_id, "monitor")

    results: list[CheckResult] = []
    for name, func in CHECKS.items():
        if not enabled:
            result = CheckResult(name, "DISABLED", details={"monitoring_enabled": False})
        else:
            try:
                result = func(client, config, settings.gcp.project_id)
            except Exception as exc:  # noqa: BLE001 - one broken check must not hide the rest
                result = CheckResult(
                    name,
                    "NO_DATA",
                    severity="WARNING",
                    details={"error_type": type(exc).__name__, "error": str(exc)[:300]},
                )
        results.append(result)

        emit_event(
            "monitor_evaluation",
            severity="ERROR" if result.status == "FAIL" else "INFO",
            component="monitor",
            environment=environment,
            check_name=result.check_name,
            status=result.status,
            observed_value=result.observed_value,
            threshold=result.threshold,
            details=result.details,
        )
        if persist:
            evaluation = MonitorEvaluationRecord(
                evaluation_id=f"{result.check_name}-{uuid.uuid4().hex[:12]}",
                check_name=result.check_name,
                environment=environment,
                status=result.status,
                severity=result.severity,
                observed_value=result.observed_value,
                threshold=result.threshold,
                incident_key=f"atlas-{result.check_name}",
                source="atlas_observability_monitor",
                evaluated_at=now,
                window_start=window_start,
                window_end=window_end,
                details_json=json.dumps(result.details, default=repr) if result.details else None,
            )
            try:
                upsert_monitor_evaluation(evaluation, settings, client=client)
            except Exception as exc:  # noqa: BLE001 - visible degradation, no crash
                emit_event(
                    "monitor_evaluation_write_failed",
                    severity="ERROR",
                    component="monitor",
                    check_name=result.check_name,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
        if publish:
            base_labels = {"environment": environment, "mode": mode}
            publish_gauge_safely(
                settings.gcp.project_id,
                "custom.googleapis.com/atlas/monitor/check_status",
                MONITOR_STATUS_VALUES[result.status],
                {**base_labels, "check_name": result.check_name},
            )
            for metric_type, value, extra in result.extra_metrics or []:
                publish_gauge_safely(settings.gcp.project_id, metric_type, value, {**base_labels, **extra})
    return results
