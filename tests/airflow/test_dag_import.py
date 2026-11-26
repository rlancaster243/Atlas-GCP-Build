"""Airflow DAG import safety tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def test_dag_file_exists() -> None:
    dag_path = Path(__file__).resolve().parents[2] / "dags" / "atlas_batch_pipeline.py"
    assert dag_path.exists()


def test_orchestration_helpers_import_without_airflow_when_mocked(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_ROOT", str(Path(__file__).resolve().parents[2]))
    from atlas_orchestration.context import resolve_run_context_dict

    # Pin the data interval to the same day as the manual date. Without it the scheduled
    # date defaults to "today", so this test silently turned into a >7-day backfill (and
    # tripped the cost guard) once the calendar moved a week past 2026-07-15.
    ctx = resolve_run_context_dict(
        airflow_run_id="manual__2026-07-15",
        dag_id="atlas_batch_pipeline",
        data_interval_end=datetime(2026, 7, 15, 6, 0, tzinfo=UTC),
        conf={"processing_date": "2026-07-15", "batch_id": "atlas-20260715"},
    )
    assert ctx["batch_id"] == "atlas-20260715"
    assert ctx["backfill_mode"] is False
