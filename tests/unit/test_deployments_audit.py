"""Unit tests for atlas_ops.deployments audit records (Sprint 4 Phase 10)."""

from __future__ import annotations

from typing import Any

import pytest

from atlas.config.settings import load_settings
from atlas.ops.deployments import (
    DeploymentRecord,
    finalize_deployment,
    start_deployment,
    upsert_deployment,
)


class FakeJob:
    def result(self) -> list[Any]:
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


def _record(**overrides: Any) -> DeploymentRecord:
    base: dict[str, Any] = {
        "deployment_id": "atlas-dev-20260718-abc123",
        "git_sha": "a" * 40,
        "environment": "atlas-dev",
        "deployment_type": "deploy",
        "started_at": "2026-07-18T21:00:00+00:00",
        "status": "RUNNING",
    }
    base.update(overrides)
    return DeploymentRecord(**base)


def test_upsert_uses_merge_keyed_by_deployment_id() -> None:
    client = FakeClient()
    upsert_deployment(_record(), SETTINGS, client=client)
    assert len(client.queries) == 1
    sql = client.queries[0]
    assert "MERGE" in sql
    assert "atlas_ops.deployments" in sql
    assert "target.deployment_id = source.deployment_id" in sql


def test_upsert_rejects_unknown_status_and_type() -> None:
    client = FakeClient()
    with pytest.raises(ValueError, match="Unsupported deployment status"):
        upsert_deployment(_record(status="EXPLODED"), SETTINGS, client=client)
    with pytest.raises(ValueError, match="Unsupported deployment type"):
        upsert_deployment(_record(deployment_type="yolo"), SETTINGS, client=client)
    assert client.queries == []


def test_start_deployment_writes_running_row() -> None:
    client = FakeClient()
    record = start_deployment(
        deployment_id="d-1",
        git_sha="b" * 40,
        environment="atlas-dev",
        workflow_run_id="12345",
        settings=SETTINGS,
        client=client,
    )
    assert record.status == "RUNNING"
    assert client.params[0]["status"] == "RUNNING"
    assert client.params[0]["workflow_run_id"] == "12345"


def test_start_rollback_writes_rolling_back_row() -> None:
    client = FakeClient()
    record = start_deployment(
        deployment_id="rb-1",
        git_sha="c" * 40,
        environment="atlas-dev",
        deployment_type="rollback",
        previous_git_sha="d" * 40,
        settings=SETTINGS,
        client=client,
    )
    assert record.status == "ROLLING_BACK"
    assert client.params[0]["previous_git_sha"] == "d" * 40


def test_finalize_is_idempotent_per_deployment_id() -> None:
    client = FakeClient()
    record = _record()
    first = finalize_deployment(record, status="SUCCESS", settings=SETTINGS, client=client)
    second = finalize_deployment(first, status="SUCCESS", settings=SETTINGS, client=client)
    # Same deployment_id and completed_at on repeat finalization: the MERGE
    # updates the same row rather than inserting another attempt.
    assert first.deployment_id == second.deployment_id
    assert first.completed_at == second.completed_at
    assert all("WHEN MATCHED THEN UPDATE" in sql for sql in client.queries)


def test_finalize_failure_records_stage_and_sanitized_error() -> None:
    client = FakeClient()
    record = _record()
    finalize_deployment(
        record,
        status="FAILED",
        failure_stage="smoke_validation",
        error_type="SmokeFailure",
        error_summary='dbt exploded with keyfile {"private_key": "SECRET"} attached',
        settings=SETTINGS,
        client=client,
    )
    params = client.params[0]
    assert params["status"] == "FAILED"
    assert params["failure_stage"] == "smoke_validation"
    assert "SECRET" not in (params["error_summary"] or "")
    assert "[REDACTED]" in params["error_summary"]


def test_rollback_links_previous_sha() -> None:
    client = FakeClient()
    record = start_deployment(
        deployment_id="rb-2",
        git_sha="0" * 40,
        environment="atlas-dev",
        deployment_type="rollback",
        previous_git_sha="f" * 40,
        settings=SETTINGS,
        client=client,
    )
    final = finalize_deployment(record, status="ROLLED_BACK", settings=SETTINGS, client=client)
    assert final.previous_git_sha == "f" * 40
    assert client.params[-1]["status"] == "ROLLED_BACK"


def test_deployments_and_pipeline_runs_are_separate_grains() -> None:
    client = FakeClient()
    upsert_deployment(_record(smoke_pipeline_run_id="atlas-smoke-abc-1"), SETTINGS, client=client)
    sql = client.queries[0]
    # Deployments reference the smoke run by id but never write pipeline_runs.
    assert "atlas_ops.deployments" in sql
    assert "pipeline_runs" not in sql
    assert client.params[0]["smoke_pipeline_run_id"] == "atlas-smoke-abc-1"
