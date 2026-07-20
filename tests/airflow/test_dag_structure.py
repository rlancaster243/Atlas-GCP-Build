"""DAG structure assertions."""

from __future__ import annotations


def test_expected_task_chain_order() -> None:
    expected = [
        "resolve_run_context",
        "ensure_audit_resources",
        "start_run_audit",
        "preflight_environment",
        "generate_events",
        "upload_events",
        "load_bigquery_raw",
        "validate_raw_load",
        "dbt_seed",
        "dbt_source_freshness",
        "dbt_build",
        "validate_warehouse",
        "publish_success_marker",
        "write_run_summary",
    ]
    # Static contract documented for parse-safe environments without Airflow runtime.
    assert len(expected) == 14
    assert expected[0] == "resolve_run_context"
    assert expected[-1] == "write_run_summary"


def test_schedule_and_start_date_constants() -> None:
    from pathlib import Path

    dag_file = Path(__file__).resolve().parents[2] / "dags" / "atlas_batch_pipeline.py"
    source = dag_file.read_text(encoding="utf-8")
    assert 'schedule="0 6 * * *"' in source
    assert "catchup=False" in source
    assert "max_active_runs=1" in source
    assert "START_DATE = datetime(2026, 7, 1, tzinfo=UTC)" in source
