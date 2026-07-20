"""Run context resolution tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from atlas_orchestration.context import resolve_processing_date, resolve_run_context_dict


def test_resolve_processing_date_from_manual_override() -> None:
    assert resolve_processing_date(None, manual_processing_date="2026-07-10") == "2026-07-10"


def test_backfill_mode_when_manual_date_differs(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_ROOT", "/tmp/atlas")
    recent = (datetime.now(tz=UTC).date() - timedelta(days=2)).isoformat()
    ctx = resolve_run_context_dict(
        airflow_run_id="manual__1",
        dag_id="atlas_batch_pipeline",
        conf={"processing_date": recent, "batch_id": f"atlas-{recent.replace('-', '')}"},
    )
    assert ctx["backfill_mode"] is True


def test_backfill_beyond_policy_window_is_blocked(monkeypatch) -> None:
    """S6-COST-002: an oversized backfill window is rejected without override."""
    from atlas.observability.cost_guards import BACKFILL_OVERRIDE_VAR, CostGuardViolation

    monkeypatch.setenv("ATLAS_ROOT", "/tmp/atlas")
    monkeypatch.delenv(BACKFILL_OVERRIDE_VAR, raising=False)
    old = (datetime.now(tz=UTC).date() - timedelta(days=30)).isoformat()
    with pytest.raises(CostGuardViolation, match="exceeds the .*-day policy"):
        resolve_run_context_dict(
            airflow_run_id="manual__2",
            dag_id="atlas_batch_pipeline",
            conf={"processing_date": old, "batch_id": f"atlas-{old.replace('-', '')}"},
        )


def test_backfill_beyond_policy_window_allowed_with_override(monkeypatch) -> None:
    from atlas.observability.cost_guards import BACKFILL_OVERRIDE_VAR

    monkeypatch.setenv("ATLAS_ROOT", "/tmp/atlas")
    monkeypatch.setenv(BACKFILL_OVERRIDE_VAR, "true")
    old = (datetime.now(tz=UTC).date() - timedelta(days=30)).isoformat()
    ctx = resolve_run_context_dict(
        airflow_run_id="manual__3",
        dag_id="atlas_batch_pipeline",
        conf={"processing_date": old, "batch_id": f"atlas-{old.replace('-', '')}"},
    )
    assert ctx["backfill_mode"] is True
