"""Unit tests for validation reporting."""

from __future__ import annotations

from atlas.config.settings import load_settings
from atlas.validation.checks import ValidationCheck, ValidationReport, validate_anomaly_detection


def test_validate_anomaly_detection_requires_exact_seeded_counts() -> None:
    settings = load_settings()
    base_checks = [
        ValidationCheck("duplicates", "FAIL", 50, 50, ""),
        ValidationCheck("null_user_ids", "FAIL", 500, 500, ""),
        ValidationCheck("invalid_country_codes", "FAIL", 200, 200, ""),
        ValidationCheck("future_timestamps", "FAIL", 150, 150, ""),
        ValidationCheck("late_arriving_events", "FAIL", 300, 300, ""),
    ]
    report = ValidationReport("run-1", "FAIL", base_checks)
    enriched = validate_anomaly_detection(report, settings)
    acceptance = [check for check in enriched.checks if check.name.startswith("acceptance_")]
    assert len(acceptance) == 5
    assert all(check.status == "PASS" for check in acceptance)


def test_validate_anomaly_detection_rejects_inflated_future_timestamp_count() -> None:
    settings = load_settings()
    base_checks = [
        ValidationCheck("duplicates", "FAIL", 50, 50, ""),
        ValidationCheck("null_user_ids", "FAIL", 500, 500, ""),
        ValidationCheck("invalid_country_codes", "FAIL", 200, 200, ""),
        ValidationCheck("future_timestamps", "FAIL", 150, 15028, ""),
        ValidationCheck("late_arriving_events", "FAIL", 300, 300, ""),
    ]
    report = ValidationReport("run-1", "FAIL", base_checks)
    enriched = validate_anomaly_detection(report, settings)
    future_acceptance = next(
        check for check in enriched.checks if check.name == "acceptance_future_timestamp_detection"
    )
    assert future_acceptance.status == "FAIL"
    assert future_acceptance.expected == 150
    assert future_acceptance.actual == 15028
