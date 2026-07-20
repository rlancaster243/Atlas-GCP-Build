"""Integration tests for local pipeline execution."""

from __future__ import annotations

from atlas.config.settings import load_settings
from atlas.pipeline.orchestrator import run_pipeline


def test_local_generate_only_pipeline() -> None:
    settings = load_settings()
    result = run_pipeline(
        settings,
        skip_upload=True,
        skip_load=True,
        skip_validation=True,
    )
    assert result.generation.event_count == 50000
    assert result.upload is None
    assert result.load is None
    assert result.validation is None
    assert result.log_file.exists()
