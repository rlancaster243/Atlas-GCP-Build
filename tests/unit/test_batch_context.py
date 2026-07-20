"""Unit tests for batch context resolution."""

from __future__ import annotations

import pytest

from atlas.batch.context import (
    build_pipeline_run_id,
    default_batch_id,
    default_seed_for_date,
    resolve_batch_context,
    validate_batch_id,
)


def test_default_batch_id_from_processing_date() -> None:
    assert default_batch_id("2026-07-15") == "atlas-20260715"


def test_default_seed_is_deterministic() -> None:
    assert default_seed_for_date("2026-07-15") == default_seed_for_date("2026-07-15")


def test_validate_batch_id_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        validate_batch_id("bad batch")


def test_resolve_batch_context_builds_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_ROOT", str(tmp_path))
    ctx = resolve_batch_context(
        processing_date="2026-07-15",
        batch_id="atlas-20260715",
        airflow_run_id="manual__2026-07-15T06:00:00+00:00",
    )
    assert ctx.batch_id == "atlas-20260715"
    assert ctx.pipeline_run_id.startswith("atlas-airflow-20260715-")
    assert ctx.local_file_path == tmp_path / "data/runs/atlas-20260715/events.jsonl"


def test_build_pipeline_run_id_sanitizes_airflow_run_id() -> None:
    run_id = build_pipeline_run_id("2026-07-15", "manual__2026-07-15T06:00:00+00:00")
    assert "manual__2026-07-15T06" in run_id
