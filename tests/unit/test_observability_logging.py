"""Contract tests for the Sprint 5 structured logging module."""

from __future__ import annotations

import io
import json
from datetime import datetime

import pytest

from atlas.observability.logging import (
    ALLOWED_FIELDS,
    CORRELATION_FIELDS,
    EVENT_MARKER,
    ContractViolation,
    build_event,
    correlation_fields_from_context,
    emit_event,
    new_correlation_id,
)


def test_minimal_event_schema() -> None:
    event = build_event("task_started", component="step_runner")
    assert event[EVENT_MARKER] is True
    assert event["event_type"] == "task_started"
    assert event["severity"] == "INFO"
    assert event["component"] == "step_runner"
    # UTC ISO-8601 timestamp
    parsed = datetime.fromisoformat(event["timestamp"])
    assert parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0


def test_correlation_hierarchy_fields_accepted() -> None:
    event = build_event(
        "task_finished",
        deployment_id="dep-1",
        airflow_run_id="run-1",
        pipeline_run_id="pr-1",
        batch_id="b-1",
        task_id="load",
        attempt_number=2,
    )
    for field in CORRELATION_FIELDS:
        assert field in event
    assert event["attempt_number"] == 2


def test_unknown_field_dropped_and_noted() -> None:
    event = build_event("task_finished", bogus_field="x")
    assert "bogus_field" not in event
    assert "field:bogus_field" in event["contract_violations"]


def test_unknown_field_raises_in_strict_mode() -> None:
    with pytest.raises(ContractViolation):
        build_event("task_finished", strict=True, bogus_field="x")


def test_invalid_severity_normalized_or_strict() -> None:
    event = build_event("x", severity="LOUD")
    assert event["severity"] == "INFO"
    assert "severity:LOUD" in event["contract_violations"]
    with pytest.raises(ContractViolation):
        build_event("x", severity="LOUD", strict=True)


def test_error_message_is_sanitized_and_truncated() -> None:
    # Concatenated so the repo secret scanner never sees a contiguous PEM header.
    pem_header = "-----BEGIN " + "PRIVATE KEY-----"
    secret = '{"private_key": "' + pem_header + 'abc"}' + "x" * 5000
    event = build_event("task_failed", error_message=secret, error_type="RuntimeError")
    assert "BEGIN PRIVATE KEY" not in event["error_message"]
    assert "[REDACTED]" in event["error_message"]
    assert len(event["error_message"]) <= 2000


def test_no_secret_tokens_survive_common_fields() -> None:
    event = build_event(
        "deploy_failed",
        error_message="Authorization: Bearer abc123token failed",
    )
    assert "abc123token" not in json.dumps(event)


def test_non_serializable_values_degrade_to_strings() -> None:
    class Weird:
        def __repr__(self) -> str:
            return "<weird object>"

    event = build_event("x", details={"obj": Weird()})
    assert event["details"]["obj"] == "<weird object>"
    json.dumps(event)  # must be serializable end to end


def test_details_truncation() -> None:
    event = build_event("x", details={"blob": "y" * 10000})
    assert event["details"]["truncated"] is True


def test_int_fields_coerced() -> None:
    event = build_event("x", rows_loaded="50000", duration_ms=12.7)
    assert event["rows_loaded"] == 50000
    assert event["duration_ms"] == 12


def test_emit_writes_one_json_line() -> None:
    stream = io.StringIO()
    emit_event("task_started", stream=stream, pipeline_run_id="pr-1")
    lines = stream.getvalue().strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["event_type"] == "task_started"
    assert parsed["pipeline_run_id"] == "pr-1"


def test_emit_never_raises_and_writes_fallback(monkeypatch) -> None:
    stream = io.StringIO()

    def boom(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("emitter broke")

    monkeypatch.setattr("atlas.observability.logging.build_event", boom)
    result = emit_event("task_started", stream=stream)
    assert result is None
    parsed = json.loads(stream.getvalue().strip())
    assert parsed["event_type"] == "telemetry_emit_failed"
    assert parsed["severity"] == "ERROR"


def test_field_names_are_deterministic() -> None:
    # The allowlist is the contract; renaming a field is a breaking change
    # that must be made consciously here and in downstream log filters.
    expected_core = {
        "timestamp",
        "severity",
        "event_type",
        "component",
        "environment",
        "git_sha",
        "deployment_id",
        "dag_id",
        "task_id",
        "airflow_run_id",
        "pipeline_run_id",
        "batch_id",
        "processing_date",
        "attempt_number",
        "status",
        "duration_ms",
        "rows_generated",
        "rows_loaded",
        "rows_accepted",
        "rows_rejected",
        "fact_rows",
        "mart_event_count",
        "check_name",
        "observed_value",
        "threshold",
        "error_type",
        "error_message",
        "correlation_id",
    }
    assert expected_core <= set(ALLOWED_FIELDS)


def test_correlation_extraction_from_context() -> None:
    ctx = {
        "pipeline_run_id": "pr-1",
        "batch_id": "b-1",
        "airflow_run_id": "ar-1",
        "processing_date": "2026-07-19",
        "unrelated": "x",
    }
    fields = correlation_fields_from_context(ctx)
    assert fields == {"pipeline_run_id": "pr-1", "batch_id": "b-1", "airflow_run_id": "ar-1"}


def test_new_correlation_id_unique() -> None:
    assert new_correlation_id() != new_correlation_id()


def test_cloud_emit_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the opt-in env var, no Cloud Logging client is ever touched."""
    import atlas.observability.logging as obs_logging

    monkeypatch.delenv(obs_logging.CLOUD_EMIT_ENV_VAR, raising=False)
    calls: list[dict] = []
    monkeypatch.setattr(obs_logging, "_emit_to_cloud", lambda e: calls.append(e))
    out = io.StringIO()
    assert emit_event("task_started", stream=out) is not None
    assert calls == []


def test_cloud_emit_enabled_forwards_event(monkeypatch: pytest.MonkeyPatch) -> None:
    import atlas.observability.logging as obs_logging

    monkeypatch.setenv(obs_logging.CLOUD_EMIT_ENV_VAR, "true")
    calls: list[dict] = []
    monkeypatch.setattr(obs_logging, "_emit_to_cloud", lambda e: calls.append(e))
    out = io.StringIO()
    emit_event("task_started", stream=out, pipeline_run_id="pr-1")
    assert len(calls) == 1
    assert calls[0]["pipeline_run_id"] == "pr-1"


def test_cloud_emit_failure_does_not_break_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    import atlas.observability.logging as obs_logging

    monkeypatch.setenv(obs_logging.CLOUD_EMIT_ENV_VAR, "true")

    def _boom(event: dict) -> None:
        raise RuntimeError("cloud logging down")

    monkeypatch.setattr(obs_logging, "_emit_to_cloud", _boom)
    out = io.StringIO()
    # emit_event must not raise; the original contract line is printed before
    # the cloud fan-out, so it is always present in the stream.
    emit_event("task_started", stream=out)
    first_line = out.getvalue().splitlines()[0]
    assert json.loads(first_line)["event_type"] == "task_started"
