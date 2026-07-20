"""Recovery-action audit tests (Sprint 6, Phase 4 / ADR-014)."""

from __future__ import annotations

from typing import Any

import pytest

from atlas.config.settings import load_settings
from atlas.ops.recovery_actions import (
    ALLOWED_ACTION_TYPES,
    RecoveryActionRecord,
    finalize_recovery_action,
    start_recovery_action,
    upsert_recovery_action,
)


class FakeJob:
    def result(self) -> list:
        return []


class FakeClient:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.params: list[dict[str, Any]] = []

    def query(self, sql: str, job_config: Any = None) -> FakeJob:
        self.queries.append(sql)
        if job_config is not None:
            self.params.append({p.name: p.value for p in job_config.query_parameters})
        return FakeJob()


SETTINGS = load_settings()


def _record(**overrides: Any) -> RecoveryActionRecord:
    base: dict[str, Any] = {
        "recovery_id": "rec-1",
        "action_type": "RERUN_BATCH",
        "status": "RUNNING",
        "scenario_id": "S6-ING-001",
        "batch_id": "atlas-s6-a",
        "verification_status": "PENDING",
    }
    base.update(overrides)
    return RecoveryActionRecord(**base)


def test_upsert_uses_idempotent_merge_on_recovery_id() -> None:
    client = FakeClient()
    upsert_recovery_action(_record(), SETTINGS, client=client)
    sql = client.queries[0]
    assert "MERGE" in sql and "atlas_ops.recovery_actions" in sql
    assert "ON target.recovery_id = @recovery_id" in sql


def test_repeated_finalization_is_merge_not_duplicate_insert() -> None:
    client = FakeClient()
    record = _record()
    for _ in range(3):
        finalize_recovery_action(
            record, status="SUCCESS", verification_status="VERIFIED", client=client, settings=SETTINGS
        )
    assert all("WHEN MATCHED THEN" in sql for sql in client.queries)
    assert {p["recovery_id"] for p in client.params} == {"rec-1"}


def test_success_requires_verified_status() -> None:
    client = FakeClient()
    with pytest.raises(ValueError, match="requires verification_status=VERIFIED"):
        upsert_recovery_action(
            _record(status="SUCCESS", verification_status="PENDING"), SETTINGS, client=client
        )
    with pytest.raises(ValueError, match="requires verification_status=VERIFIED"):
        finalize_recovery_action(
            _record(), status="SUCCESS", verification_status="FAILED", client=client, settings=SETTINGS
        )
    assert client.queries == []


def test_partial_and_failed_states_allowed_without_verification() -> None:
    client = FakeClient()
    finalize_recovery_action(
        _record(), status="PARTIAL", verification_status="FAILED", client=client, settings=SETTINGS
    )
    finalize_recovery_action(
        _record(recovery_id="rec-2"),
        status="FAILED",
        verification_status="SKIPPED",
        error_type="RuntimeError",
        error_summary="repair query failed",
        client=client,
        settings=SETTINGS,
    )
    assert len(client.queries) == 2


def test_invalid_action_type_and_status_rejected() -> None:
    client = FakeClient()
    with pytest.raises(ValueError, match="Unsupported recovery action type"):
        upsert_recovery_action(_record(action_type="WISH_HARDER"), SETTINGS, client=client)
    with pytest.raises(ValueError, match="Unsupported recovery status"):
        upsert_recovery_action(_record(status="MAYBE"), SETTINGS, client=client)
    assert client.queries == []


def test_all_controlled_action_types_accepted() -> None:
    client = FakeClient()
    for i, action in enumerate(sorted(ALLOWED_ACTION_TYPES)):
        upsert_recovery_action(_record(recovery_id=f"rec-{i}", action_type=action), SETTINGS, client=client)
    assert len(client.queries) == len(ALLOWED_ACTION_TYPES)


def test_error_summary_is_sanitized() -> None:
    client = FakeClient()
    secret = "-----BEGIN " + "PRIVATE KEY-----abc"
    upsert_recovery_action(_record(status="FAILED", error_summary=f"boom {secret}"), SETTINGS, client=client)
    assert "BEGIN PRIVATE KEY" not in client.params[0]["error_summary"]
    assert "[REDACTED]" in client.params[0]["error_summary"]


def test_start_links_incident_scenario_and_pipeline_grains(capsys: pytest.CaptureFixture[str]) -> None:
    client = FakeClient()
    record = start_recovery_action(
        recovery_id="rec-9",
        action_type="RECONSTRUCT_AUDIT",
        incident_id="0.abc123",
        scenario_id="S6-AIR-003",
        pipeline_run_id="atlas-s6-air003-run",
        batch_id="atlas-s6-air003",
        deployment_id="atlas-dev-20260720T000000Z-deadbeef",
        settings=SETTINGS,
        client=client,
    )
    assert record.status == "RUNNING"
    assert record.verification_status == "PENDING"
    params = client.params[0]
    assert params["incident_id"] == "0.abc123"
    assert params["scenario_id"] == "S6-AIR-003"
    assert params["deployment_id"] == "atlas-dev-20260720T000000Z-deadbeef"
    assert "recovery_action_started" in capsys.readouterr().out
