"""Unit tests for atlas_ops.task_events (Sprint 5 Phase 3)."""

from __future__ import annotations

from typing import Any

import pytest

from atlas.config.settings import load_settings
from atlas.ops.task_events import (
    EXPECTED_TERMINAL_TASKS,
    TaskEventRecord,
    record_task_event_safely,
    telemetry_completeness,
    upsert_task_event,
)


class FakeJob:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []

    def result(self) -> list[dict[str, Any]]:
        return self._rows


class FakeClient:
    def __init__(self, select_rows: list[dict[str, Any]] | None = None) -> None:
        self.queries: list[str] = []
        self.params: list[dict[str, Any]] = []
        self._select_rows = select_rows or []

    def query(self, sql: str, job_config: Any = None) -> FakeJob:
        self.queries.append(sql)
        if job_config is not None:
            self.params.append({p.name: p.value for p in job_config.query_parameters})
        if sql.strip().upper().startswith("SELECT"):
            return FakeJob(self._select_rows)
        return FakeJob()


class BrokenClient:
    def query(self, sql: str, job_config: Any = None) -> FakeJob:
        raise RuntimeError("BigQuery unavailable")


SETTINGS = load_settings()


def _record(**overrides: Any) -> TaskEventRecord:
    base: dict[str, Any] = {
        "pipeline_run_id": "pr-1",
        "task_id": "load_bigquery_raw",
        "attempt_number": 1,
        "event_type": "SUCCESS",
        "batch_id": "b-1",
        "status": "SUCCESS",
    }
    base.update(overrides)
    return TaskEventRecord(**base)


def test_upsert_uses_merge_on_full_attempt_key() -> None:
    client = FakeClient()
    upsert_task_event(_record(), SETTINGS, client=client)
    sql = client.queries[0]
    assert "MERGE" in sql and "atlas_ops.task_events" in sql
    for key in ("task_id = @task_id", "attempt_number = @attempt_number", "event_type = @event_type"):
        assert key in sql


def test_first_attempt_success_row() -> None:
    client = FakeClient()
    upsert_task_event(_record(), SETTINGS, client=client)
    assert client.params[0]["attempt_number"] == 1
    assert client.params[0]["event_type"] == "SUCCESS"


def test_retry_then_success_are_distinct_rows() -> None:
    client = FakeClient()
    upsert_task_event(
        _record(attempt_number=1, event_type="FAILED", status="FAILED"), SETTINGS, client=client
    )
    upsert_task_event(_record(attempt_number=2, event_type="SUCCESS"), SETTINGS, client=client)
    # Different attempt numbers hit different MERGE keys: two writes, two keys.
    assert (client.params[0]["attempt_number"], client.params[0]["event_type"]) == (1, "FAILED")
    assert (client.params[1]["attempt_number"], client.params[1]["event_type"]) == (2, "SUCCESS")


def test_repeated_callback_is_idempotent_merge_not_insert() -> None:
    client = FakeClient()
    for _ in range(3):
        upsert_task_event(_record(event_type="FAILED", status="FAILED"), SETTINGS, client=client)
    assert all("WHEN MATCHED THEN" in sql for sql in client.queries)
    keys = {(p["pipeline_run_id"], p["task_id"], p["attempt_number"], p["event_type"]) for p in client.params}
    assert len(keys) == 1


def test_invalid_event_type_and_attempt_rejected() -> None:
    client = FakeClient()
    with pytest.raises(ValueError, match="Unsupported task event type"):
        upsert_task_event(_record(event_type="EXPLODED"), SETTINGS, client=client)
    with pytest.raises(ValueError, match="attempt_number"):
        upsert_task_event(_record(attempt_number=0), SETTINGS, client=client)
    assert client.queries == []


def test_error_message_is_sanitized() -> None:
    client = FakeClient()
    upsert_task_event(
        _record(
            event_type="FAILED",
            status="FAILED",
            # Concatenated so the repo secret scanner never sees a contiguous PEM header.
            error_message='failed: {"private_key": "' + "-----BEGIN " + 'PRIVATE KEY-----xyz"}',
        ),
        SETTINGS,
        client=client,
    )
    assert "BEGIN PRIVATE KEY" not in client.params[0]["error_message"]
    assert "[REDACTED]" in client.params[0]["error_message"]


def test_missing_audit_backend_returns_false_and_emits_fallback(capsys) -> None:
    ok = record_task_event_safely(_record(), SETTINGS, client=BrokenClient())
    assert ok is False
    out = capsys.readouterr().out
    assert "task_telemetry_write_failed" in out
    assert "BigQuery unavailable" in out


def test_skipped_and_upstream_failed_event_types_allowed() -> None:
    client = FakeClient()
    upsert_task_event(_record(event_type="SKIPPED", status="SKIPPED"), SETTINGS, client=client)
    upsert_task_event(
        _record(event_type="UPSTREAM_FAILED", status="UPSTREAM_FAILED"), SETTINGS, client=client
    )
    assert len(client.queries) == 2


def _events(*rows: tuple[str, str]) -> list[dict[str, Any]]:
    return [{"task_id": t, "event_type": e} for t, e in rows]


def test_telemetry_completeness_all_terminal() -> None:
    rows = _events(*[(t, "SUCCESS") for t in EXPECTED_TERMINAL_TASKS])
    client = FakeClient(select_rows=rows)
    report = telemetry_completeness("pr-1", SETTINGS, client=client)
    assert report["complete"] is True
    assert report["missing_terminal"] == []


def test_telemetry_completeness_detects_missing_and_started_only() -> None:
    rows = _events(
        ("resolve_run_context", "SUCCESS"),
        ("generate_events", "STARTED"),
    )
    client = FakeClient(select_rows=rows)
    report = telemetry_completeness("pr-1", SETTINGS, client=client)
    assert report["complete"] is False
    assert "generate_events" in report["missing_terminal"]
    assert report["started_without_terminal"] == ["generate_events"]


def test_telemetry_completeness_counts_failed_as_terminal() -> None:
    rows = _events(*[(t, "FAILED" if t == "dbt_build" else "SUCCESS") for t in EXPECTED_TERMINAL_TASKS])
    client = FakeClient(select_rows=rows)
    report = telemetry_completeness("pr-1", SETTINGS, client=client)
    assert report["complete"] is True
