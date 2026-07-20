"""Sprint 7 Phase 12: cost-control loading and static checks."""

from __future__ import annotations

import pytest

from atlas.observability import cost_guard
from atlas.observability.cost_guards import CostGuardViolation


def test_cost_controls_load_and_have_required_fields() -> None:
    controls = cost_guard.load_cost_controls()
    for env in ("atlas-dev", "atlas-ci"):
        c = controls["environments"][env]
        for field in (
            "max_query_bytes",
            "max_performance_suite_bytes",
            "max_backfill_days",
            "require_partition_filter_assets",
            "temporary_dataset_ttl_hours",
            "log_retention_days",
        ):
            assert field in c, f"{env} missing {field}"


def test_max_query_bytes_positive() -> None:
    assert cost_guard.max_query_bytes("atlas-dev") == 1073741824


def test_unknown_environment_raises() -> None:
    with pytest.raises(CostGuardViolation):
        cost_guard.environment_controls("does-not-exist")


def test_performance_suite_env_override(monkeypatch) -> None:
    monkeypatch.setenv(cost_guard.SUITE_BYTES_ENV, "123456")
    assert cost_guard.max_performance_suite_bytes("atlas-dev") == 123456


def test_partition_filter_detected() -> None:
    assert cost_guard.has_partition_filter("select * from t where event_date = '2026-07-19'")
    assert cost_guard.has_partition_filter(
        "select * from t where user_id = 'u' and processing_date >= '2026-07-01'"
    )


def test_partition_filter_absent() -> None:
    assert not cost_guard.has_partition_filter("select count(*) from t")
    assert not cost_guard.has_partition_filter("select * from t where user_id = 'u'")


def test_required_partition_filter_missing_raises() -> None:
    with pytest.raises(CostGuardViolation):
        cost_guard.check_partition_filter("select count(*) from `p.atlas_raw.events`", "atlas_raw.events")


def test_required_partition_filter_present_ok() -> None:
    cost_guard.check_partition_filter(
        "select count(*) from `p.atlas_raw.events` where event_date = '2026-07-19'",
        "atlas_raw.events",
    )


def test_non_required_asset_without_filter_ok() -> None:
    cost_guard.check_partition_filter(
        "select count(*) from `p.atlas_ops.pipeline_runs`", "atlas_ops.pipeline_runs"
    )
