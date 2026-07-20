"""Failed-task timing derivation tests (Sprint 6, Phase 1).

Sprint 5 limitation: FAILED rows written by the failure callback carried NULL
started_at/completed_at/duration_ms. Timing must now come from reliable
evidence (Airflow task-instance timestamps) with recorded provenance — and
must stay NULL when no reliable evidence exists.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from atlas_orchestration.callbacks import build_callback_context, derive_callback_timing


class _TaskInstance:
    def __init__(self, start_date=None, end_date=None) -> None:
        self.task_id = "dbt_build"
        self.try_number = 1
        self.state = "failed"
        self.start_date = start_date
        self.end_date = end_date


def _meta(start_date=None, end_date=None) -> dict:
    return build_callback_context({"task_instance": _TaskInstance(start_date, end_date), "dag_run": None})


def test_exact_timing_from_task_instance_dates() -> None:
    start = datetime(2026, 7, 19, 6, 33, 54, tzinfo=UTC)
    end = start + timedelta(seconds=90)
    timing = derive_callback_timing(_meta(start, end))
    assert timing["timing_source"] == "airflow_task_instance"
    assert timing["timing_confidence"] == "exact"
    assert timing["started_at"] == start.isoformat()
    assert timing["completed_at"] == end.isoformat()
    assert timing["duration_ms"] == 90_000


def test_partial_timing_bounds_completion_with_callback_clock() -> None:
    start = datetime.now(tz=UTC) - timedelta(seconds=30)
    timing = derive_callback_timing(_meta(start, None))
    assert timing["timing_confidence"] == "partial"
    assert timing["started_at"] == start.isoformat()
    assert timing["completed_at"] is not None
    assert timing["duration_ms"] >= 29_000


def test_no_evidence_preserves_null_and_records_none_confidence() -> None:
    """Timestamps are never invented: no start date means NULL timing."""
    timing = derive_callback_timing(_meta(None, None))
    assert timing["started_at"] is None
    assert timing["completed_at"] is None
    assert timing["duration_ms"] is None
    assert timing["timing_source"] == "airflow_task_instance"
    assert timing["timing_confidence"] == "none"


def test_negative_clock_skew_clamped_to_zero() -> None:
    start = datetime.now(tz=UTC)
    timing = derive_callback_timing(_meta(start, start - timedelta(seconds=5)))
    assert timing["duration_ms"] == 0


def test_task_event_record_rejects_unknown_timing_vocabulary() -> None:
    from atlas.config.settings import load_settings
    from atlas.ops.task_events import TaskEventRecord, upsert_task_event

    class _Client:
        def query(self, sql, job_config=None):  # pragma: no cover - must not be reached
            raise AssertionError("validation must fail before any query")

    record = TaskEventRecord(
        pipeline_run_id="pr-1",
        task_id="dbt_build",
        attempt_number=1,
        event_type="FAILED",
        timing_source="vibes",
    )
    with pytest.raises(ValueError, match="Unsupported timing_source"):
        upsert_task_event(record, load_settings(), client=_Client())

    record2 = TaskEventRecord(
        pipeline_run_id="pr-1",
        task_id="dbt_build",
        attempt_number=1,
        event_type="FAILED",
        timing_source="airflow_task_instance",
        timing_confidence="pretty_sure",
    )
    with pytest.raises(ValueError, match="Unsupported timing_confidence"):
        upsert_task_event(record2, load_settings(), client=_Client())
