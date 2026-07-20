"""Unit tests for the observability monitor engine (Sprint 5 P8)."""

from __future__ import annotations

import json
from typing import Any

from atlas.config.settings import load_settings
from atlas.observability.monitor import (
    CHECK_NAMES,
    CHECKS,
    check_cost_anomaly,
    check_freshness,
    check_latest_run_state,
    check_rejection_rate,
    check_volume_deviation,
    load_config,
    run_monitor,
)

SETTINGS = load_settings()
CONFIG = load_config()


class FakeJob:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def result(self) -> list[dict[str, Any]]:
        return self._rows


class FakeClient:
    """Returns queued row sets per query, records all SQL."""

    def __init__(self, row_sets: list[list[dict[str, Any]]] | None = None) -> None:
        self._row_sets = list(row_sets or [])
        self.queries: list[str] = []

    def query(self, sql: str, job_config: Any = None) -> FakeJob:
        self.queries.append(sql)
        if sql.strip().upper().startswith("MERGE"):
            return FakeJob([])
        return FakeJob(self._row_sets.pop(0) if self._row_sets else [])


def test_check_names_and_registry_agree() -> None:
    assert set(CHECK_NAMES) == set(CHECKS)


def test_latest_run_state_fail_on_failed_run() -> None:
    client = FakeClient(
        [[{"status": "FAILED", "pipeline_run_id": "pr-1", "started_at": None, "duration_s": 100}]]
    )
    result = check_latest_run_state(client, CONFIG, "p")
    assert result.status == "FAIL" and result.severity == "CRITICAL"


def test_latest_run_state_no_data() -> None:
    assert check_latest_run_state(FakeClient([[]]), CONFIG, "p").status == "NO_DATA"


def test_freshness_thresholds() -> None:
    warn = CONFIG["freshness"]["warn_seconds"]
    fail = CONFIG["freshness"]["fail_seconds"]
    assert check_freshness(FakeClient([[{"age_s": warn - 1}]]), CONFIG, "p").status == "PASS"
    assert check_freshness(FakeClient([[{"age_s": warn + 1}]]), CONFIG, "p").status == "WARN"
    assert check_freshness(FakeClient([[{"age_s": fail + 1}]]), CONFIG, "p").status == "FAIL"
    assert check_freshness(FakeClient([[{"age_s": None}]]), CONFIG, "p").status == "NO_DATA"


def test_volume_deviation_classification() -> None:
    def result_for(latest: int, baseline: int | None):
        return check_volume_deviation(
            FakeClient([[{"latest_rows": latest, "baseline_rows": baseline}]]), CONFIG, "p"
        )

    assert result_for(50000, 50000).status == "PASS"
    assert result_for(20000, 50000).status == "WARN"  # 60 % deviation
    assert result_for(5000, 50000).status == "FAIL"  # 90 % deviation
    assert result_for(50000, None).status == "NO_DATA"
    assert result_for(50000, 10).status == "NO_DATA"  # baseline below floor


def test_rejection_rate_classification() -> None:
    def result_for(rejected: int):
        rows = [{"rows_loaded": 50000, "rows_accepted": 50000 - rejected, "rows_rejected": rejected}]
        return check_rejection_rate(FakeClient([rows]), CONFIG, "p")

    assert result_for(5000).status == "PASS"  # 10 %
    assert result_for(12500).status == "WARN"  # 25 %
    assert result_for(20000).status == "FAIL"  # 40 %


def test_cost_anomaly_below_floor_passes() -> None:
    rows = [{"window_bytes": 10_000, "window_jobs": 5, "baseline_daily_bytes": 100}]
    result = check_cost_anomaly(FakeClient([rows]), CONFIG, "p")
    assert result.status == "PASS"
    assert result.details["reason"] == "below absolute floor"


def test_cost_anomaly_ratio_fail() -> None:
    floor = CONFIG["cost"]["min_bytes_billed"]
    rows = [{"window_bytes": floor * 20, "window_jobs": 5, "baseline_daily_bytes": floor}]
    assert check_cost_anomaly(FakeClient([rows]), CONFIG, "p").status == "FAIL"


def test_run_monitor_disabled_emits_disabled_everywhere(capsys) -> None:
    config = json.loads(json.dumps(CONFIG))
    config["monitoring_enabled"] = False
    results = run_monitor(settings=SETTINGS, client=FakeClient(), config=config, persist=False, publish=False)
    assert {r.status for r in results} == {"DISABLED"}
    assert len(results) == len(CHECK_NAMES)


def test_run_monitor_one_broken_check_does_not_hide_others() -> None:
    class ExplodingClient(FakeClient):
        def query(self, sql: str, job_config: Any = None) -> FakeJob:
            raise RuntimeError("backend down")

    results = run_monitor(
        settings=SETTINGS, client=ExplodingClient(), config=CONFIG, persist=False, publish=False
    )
    assert len(results) == len(CHECK_NAMES)
    assert all(r.status in {"NO_DATA"} for r in results)


def test_drill_override_via_env(monkeypatch) -> None:
    monkeypatch.setenv(
        "ATLAS_OBSERVABILITY_OVERRIDES_JSON",
        json.dumps({"freshness": {"fail_seconds": 60}, "runtime_mode": "drill"}),
    )
    config = load_config()
    assert config["freshness"]["fail_seconds"] == 60
    assert config["runtime_mode"] == "drill"
    # untouched sections survive
    assert config["volume"]["baseline_window_runs"] == CONFIG["volume"]["baseline_window_runs"]


def test_config_defaults_are_sane() -> None:
    assert CONFIG["monitoring_enabled"] is True
    assert CONFIG["runtime_mode"] == "normal"
    assert CONFIG["freshness"]["warn_seconds"] < CONFIG["freshness"]["fail_seconds"]
    assert CONFIG["volume"]["warn_deviation"] < CONFIG["volume"]["fail_deviation"]
    assert CONFIG["rejection_rate"]["warn"] < CONFIG["rejection_rate"]["fail"]
    assert CONFIG["cost"]["warn_ratio"] < CONFIG["cost"]["fail_ratio"]
