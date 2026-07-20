"""Atlas observability monitor DAG (Sprint 5, Phase 8).

Evaluates system health independently of the business pipeline every 30
minutes while the environment is active. Read-only except for
``atlas_ops.monitor_evaluations`` rows and Cloud Monitoring metric points.
No network calls at import time; all atlas imports happen inside the task.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from airflow.sdk import DAG, task

# Composer parity: same sys.path bootstrap as atlas_batch_pipeline (Airflow 3
# does not add the DAG file's own subfolder to sys.path).
_DAG_DIR = Path(__file__).resolve().parent
ATLAS_ROOT = Path(os.environ.get("ATLAS_ROOT", Path(__file__).resolve().parents[1]))
for _extra in (str(_DAG_DIR), str(ATLAS_ROOT / "src")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

DAG_ID = "atlas_observability_monitor"
START_DATE = datetime(2026, 7, 1, tzinfo=UTC)


@task(task_id="evaluate_monitors")
def evaluate_monitors(**context) -> dict:
    """Run all monitor checks; fail the task only on monitor infrastructure errors.

    A FAIL evaluation is a *finding*, not a task failure: alerting reacts to
    the published check_status metrics, and failing this task would only
    silence future evaluations.
    """
    src = str(ATLAS_ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from atlas.observability.monitor import load_config, run_monitor

    config = load_config()
    data_interval_start = context.get("data_interval_start")
    data_interval_end = context.get("data_interval_end")
    results = run_monitor(
        config=config,
        window_start=data_interval_start.isoformat() if data_interval_start else None,
        window_end=data_interval_end.isoformat() if data_interval_end else None,
    )
    summary = {r.check_name: r.status for r in results}
    print({"monitor_summary": summary, "monitoring_enabled": config.get("monitoring_enabled")})
    return summary


with DAG(
    dag_id=DAG_ID,
    schedule="*/30 * * * *",
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    # Deployments land paused; unpaused deliberately during acceptance windows.
    is_paused_upon_creation=True,
    default_args={"owner": "atlas", "retries": 1},
    tags=["atlas", "sprint5", "observability"],
) as dag:
    evaluate_monitors()
