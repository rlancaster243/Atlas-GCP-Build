"""Acceptance tests for Sprint 1 definition of done (local portions)."""

from __future__ import annotations

import json
from pathlib import Path

from atlas.config.settings import load_settings
from atlas.generator.events import generate_events
from atlas.pipeline.orchestrator import run_pipeline


def test_sprint1_local_artifacts_exist() -> None:
    settings = load_settings()
    result = run_pipeline(settings, skip_upload=True, skip_load=True, skip_validation=True)

    assert result.generation.output_path.exists()
    lines = result.generation.output_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 50000

    first = json.loads(lines[0])
    assert "ingested_at" not in first
    assert {
        "event_id",
        "user_id",
        "event_name",
        "event_timestamp",
        "event_date",
        "country_code",
        "platform",
        "app_version",
    }.issubset(first.keys())

    assert result.log_file.exists()
    log_lines = result.log_file.read_text(encoding="utf-8").strip().splitlines()
    assert any('"step": "generate"' in line for line in log_lines)


def test_generator_anomaly_profile_matches_config() -> None:
    settings = load_settings()
    result = generate_events(settings)
    profile = settings.anomaly_profile
    assert result.anomaly_counts["null_user_ids"] == profile.expected_count("null_user_ids")
    assert result.anomaly_counts["invalid_country_codes"] == profile.expected_count("invalid_country_codes")


def test_repository_layout() -> None:
    root = Path(__file__).resolve().parents[2]
    for relative in ["src", "data", "docs", "sql", "tests", "requirements.txt", "README.md", ".gitignore"]:
        assert (root / relative).exists()
