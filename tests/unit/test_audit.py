"""Unit tests for operational audit helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from atlas.ops.audit import PipelineRunRecord, sanitize_error_message, upsert_pipeline_run


def test_sanitize_error_message_redacts_secrets() -> None:
    msg = "Bearer abc.def.ghi and BEGIN PRIVATE KEY"
    sanitized = sanitize_error_message(msg)
    assert "Bearer" not in sanitized
    assert "BEGIN PRIVATE KEY" not in sanitized


def test_upsert_pipeline_run_executes_merge() -> None:
    client = MagicMock()
    record = PipelineRunRecord(
        pipeline_run_id="atlas-airflow-20260715-test",
        batch_id="atlas-20260715",
        airflow_run_id="manual__1",
        dag_id="atlas_batch_pipeline",
        processing_date="2026-07-15",
        started_at="2026-07-15T06:00:00+00:00",
        completed_at=None,
        status="RUNNING",
        attempt_number=1,
    )
    upsert_pipeline_run(record, client=client)
    client.query.assert_called_once()
