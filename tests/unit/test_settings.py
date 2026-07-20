"""Unit tests for Atlas settings."""

from __future__ import annotations

from atlas.config.settings import load_settings, staging_table_id, table_fqn


def test_load_settings_defaults() -> None:
    settings = load_settings()
    assert settings.gcp.project_id == "example-gcp-project"
    assert settings.generator.event_count == 50000
    assert settings.anomaly_profile.expected_count("null_user_ids") == 500


def test_table_fqn() -> None:
    settings = load_settings()
    assert table_fqn(settings) == "example-gcp-project.atlas_raw.events"
    assert staging_table_id(settings, "atlas-run-1").endswith("_staging_atlas_run_1")
