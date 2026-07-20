"""Unit tests for quality_results / monitor_evaluations and the warehouse bridge."""

from __future__ import annotations

from typing import Any

import pytest

from atlas.config.settings import load_settings
from atlas.observability.checks import CHECK_CATEGORIES, persist_warehouse_report
from atlas.ops.quality_results import (
    MonitorEvaluationRecord,
    QualityResultRecord,
    details_to_json,
    upsert_monitor_evaluation,
    upsert_quality_result,
)
from atlas.validation.warehouse import WarehouseCheck, WarehouseReport


class FakeJob:
    def result(self) -> list[Any]:
        return []


class FakeClient:
    def __init__(self, fail: bool = False) -> None:
        self.queries: list[str] = []
        self.params: list[dict[str, Any]] = []
        self._fail = fail

    def query(self, sql: str, job_config: Any = None) -> FakeJob:
        if self._fail:
            raise RuntimeError("BigQuery unavailable")
        self.queries.append(sql)
        if job_config is not None:
            self.params.append({p.name: p.value for p in job_config.query_parameters})
        return FakeJob()


SETTINGS = load_settings()


def _quality(**overrides: Any) -> QualityResultRecord:
    base: dict[str, Any] = {
        "pipeline_run_id": "pr-1",
        "check_name": "raw_equals_classification",
        "check_category": "RECONCILIATION",
        "severity": "INFO",
        "status": "PASS",
        "evaluated_at": "2026-07-19T03:00:00+00:00",
        "batch_id": "b-1",
        "observed_value": 50000.0,
        "expected_value": 50000.0,
    }
    base.update(overrides)
    return QualityResultRecord(**base)


def test_quality_merge_keyed_by_run_and_check() -> None:
    client = FakeClient()
    upsert_quality_result(_quality(), SETTINGS, client=client)
    sql = client.queries[0]
    assert "MERGE" in sql and "atlas_ops.quality_results" in sql
    assert "target.pipeline_run_id = @pipeline_run_id" in sql
    assert "target.check_name = @check_name" in sql


def test_quality_rejects_invalid_vocabulary() -> None:
    client = FakeClient()
    with pytest.raises(ValueError, match="check category"):
        upsert_quality_result(_quality(check_category="VIBES"), SETTINGS, client=client)
    with pytest.raises(ValueError, match="quality status"):
        upsert_quality_result(_quality(status="MEH"), SETTINGS, client=client)
    with pytest.raises(ValueError, match="severity"):
        upsert_quality_result(_quality(severity="LOUD"), SETTINGS, client=client)
    assert client.queries == []


def test_quality_details_truncated() -> None:
    client = FakeClient()
    upsert_quality_result(_quality(details_json="x" * 10000), SETTINGS, client=client)
    assert len(client.params[0]["details_json"]) <= 4000


def test_monitor_evaluation_merge_keyed_by_evaluation_id() -> None:
    client = FakeClient()
    upsert_monitor_evaluation(
        MonitorEvaluationRecord(
            evaluation_id="eval-1",
            check_name="freshness",
            environment="atlas-dev",
            status="PASS",
            evaluated_at="2026-07-19T03:00:00+00:00",
            observed_value=120.0,
            threshold=93600.0,
        ),
        SETTINGS,
        client=client,
    )
    sql = client.queries[0]
    assert "atlas_ops.monitor_evaluations" in sql
    assert "target.evaluation_id = @evaluation_id" in sql


def test_monitor_evaluation_allows_no_data_and_disabled() -> None:
    client = FakeClient()
    for status in ("NO_DATA", "DISABLED"):
        upsert_monitor_evaluation(
            MonitorEvaluationRecord(
                evaluation_id=f"eval-{status}",
                check_name="freshness",
                environment="atlas-dev",
                status=status,
                evaluated_at="2026-07-19T03:00:00+00:00",
            ),
            SETTINGS,
            client=client,
        )
    assert len(client.queries) == 2


def test_monitor_evaluation_rejects_invalid_status() -> None:
    client = FakeClient()
    with pytest.raises(ValueError, match="evaluation status"):
        upsert_monitor_evaluation(
            MonitorEvaluationRecord(
                evaluation_id="eval-x",
                check_name="freshness",
                environment="atlas-dev",
                status="ON_FIRE",
                evaluated_at="2026-07-19T03:00:00+00:00",
            ),
            SETTINGS,
            client=client,
        )


def test_details_to_json_handles_non_serializable() -> None:
    class Weird:
        def __repr__(self) -> str:
            return "<weird>"

    rendered = details_to_json({"obj": Weird()})
    assert rendered is not None and "<weird>" in rendered
    assert details_to_json(None) is None


def _report(status: str = "PASS") -> WarehouseReport:
    checks = [
        WarehouseCheck(name=name, status=status, expected=1, actual=1, message="m")
        for name in CHECK_CATEGORIES
    ]
    return WarehouseReport(batch_id="b-1", overall_status=status, checks=checks)


def test_persist_warehouse_report_writes_one_row_per_check() -> None:
    client = FakeClient()
    written = persist_warehouse_report(_report(), "pr-1", settings=SETTINGS, client=client)
    assert written == len(CHECK_CATEGORIES)
    names = {p["check_name"] for p in client.params}
    assert names == set(CHECK_CATEGORIES)
    categories = {p["check_name"]: p["check_category"] for p in client.params}
    assert categories == CHECK_CATEGORIES


def test_persist_warehouse_report_failed_checks_are_critical() -> None:
    client = FakeClient()
    persist_warehouse_report(_report(status="FAIL"), "pr-1", settings=SETTINGS, client=client)
    assert all(p["severity"] == "CRITICAL" and p["status"] == "FAIL" for p in client.params)


def test_persist_warehouse_report_survives_backend_failure(capsys) -> None:
    written = persist_warehouse_report(_report(), "pr-1", settings=SETTINGS, client=FakeClient(fail=True))
    assert written == 0
    out = capsys.readouterr().out
    assert "quality_result_write_failed" in out
