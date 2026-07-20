"""BigQuery cost-guard tests (Sprint 6, Phase 12)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from atlas.observability.cost_guards import (
    BACKFILL_OVERRIDE_VAR,
    FULL_REFRESH_APPROVAL_VAR,
    CostGuardViolation,
    backfill_dates,
    enforce_dry_run_ceiling,
    estimate_query_bytes,
    guarded_query_config,
    require_full_refresh_approval,
    validate_backfill_window,
)


class FakeDryRunJob:
    def __init__(self, total_bytes: int) -> None:
        self.total_bytes_processed = total_bytes


class FakeClient:
    def __init__(self, estimate: int) -> None:
        self.estimate = estimate
        self.configs: list[Any] = []

    def query(self, sql: str, job_config: Any = None) -> FakeDryRunJob:
        self.configs.append(job_config)
        return FakeDryRunJob(self.estimate)


def test_dry_run_estimate_uses_dry_run_config() -> None:
    client = FakeClient(estimate=1234)
    assert estimate_query_bytes(client, "SELECT 1") == 1234
    assert client.configs[0].dry_run is True


def test_ceiling_blocks_unpartitioned_scan(capsys: pytest.CaptureFixture[str]) -> None:
    """S6-COST-001: an over-ceiling estimate is refused before execution."""
    client = FakeClient(estimate=5 * 1024**3)
    with pytest.raises(CostGuardViolation, match="exceeds ceiling"):
        enforce_dry_run_ceiling(client, "SELECT * FROM atlas_raw.events", max_estimated_bytes=1024**3)
    assert "cost_guard_blocked" in capsys.readouterr().out


def test_ceiling_allows_bounded_query_and_returns_estimate() -> None:
    client = FakeClient(estimate=10_000)
    assert enforce_dry_run_ceiling(client, "SELECT 1", max_estimated_bytes=1024**3) == 10_000


def test_guarded_query_config_sets_maximum_bytes_billed() -> None:
    config = guarded_query_config(maximum_bytes_billed=42, labels={"application": "atlas"})
    assert config.maximum_bytes_billed == 42
    assert config.labels == {"application": "atlas"}


def test_backfill_window_within_policy_allowed() -> None:
    days = validate_backfill_window(date(2026, 7, 10), date(2026, 7, 14), max_days=7, env={})
    assert days == 5
    assert len(backfill_dates(date(2026, 7, 10), days)) == 5


def test_backfill_window_beyond_policy_blocked_without_override() -> None:
    """S6-COST-002: unbounded backfill requires an explicit override."""
    with pytest.raises(CostGuardViolation, match="exceeds the 7-day policy"):
        validate_backfill_window(date(2026, 6, 1), date(2026, 7, 19), max_days=7, env={})


def test_backfill_window_beyond_policy_allowed_with_explicit_override() -> None:
    days = validate_backfill_window(
        date(2026, 6, 1), date(2026, 7, 19), max_days=7, env={BACKFILL_OVERRIDE_VAR: "true"}
    )
    assert days == 49


def test_backfill_override_must_be_exactly_true() -> None:
    for sloppy in ("1", "yes", "TRUEISH"):
        with pytest.raises(CostGuardViolation):
            validate_backfill_window(
                date(2026, 6, 1), date(2026, 7, 19), max_days=7, env={BACKFILL_OVERRIDE_VAR: sloppy}
            )


def test_inverted_backfill_window_rejected() -> None:
    with pytest.raises(CostGuardViolation, match="precedes start"):
        validate_backfill_window(date(2026, 7, 19), date(2026, 7, 1), env={})


def test_full_refresh_blocked_without_approval() -> None:
    """S6-COST-003: full refresh is an approved exception, never a default."""
    with pytest.raises(CostGuardViolation, match=FULL_REFRESH_APPROVAL_VAR):
        require_full_refresh_approval(env={})


def test_full_refresh_allowed_with_approval() -> None:
    require_full_refresh_approval(env={FULL_REFRESH_APPROVAL_VAR: "true"})
