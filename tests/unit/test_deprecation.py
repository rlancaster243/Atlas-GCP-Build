"""Sprint 7 Phase 6: deprecation lifecycle enforcement tests (fixtures only)."""

from __future__ import annotations

from atlas.governance.registry import deprecation_errors

POLICY = {
    "deprecation": {"minimum_window_days": 30, "require_replacement": True, "require_change_record": True}
}
CHANGES = {"CHG-20260719-deprecate-legacy"}
CONSUMERS = {
    "reader_a": {"type": "dag", "reads": ["legacy_model"]},
}


def _base_dep() -> dict:
    return {
        "replacement": "new_model",
        "owner": "atlas-data-eng",
        "deprecation_start": "2026-07-19",
        "earliest_removal_date": "2026-09-01",
        "removal_approval": "ATLAS_APPROVE_SCHEMA_MUTATION",
        "change_record": "CHG-20260719-deprecate-legacy",
    }


def test_active_asset_has_no_deprecation_errors() -> None:
    record = {"lifecycle_status": "ACTIVE"}
    assert deprecation_errors("m", record, {}, CHANGES, POLICY) == []


def test_deprecated_without_block_fails() -> None:
    record = {"lifecycle_status": "DEPRECATED"}
    errors = deprecation_errors("legacy_model", record, {}, CHANGES, POLICY)
    assert any("requires a 'deprecation' block" in e for e in errors)


def test_deprecated_without_replacement_fails() -> None:
    dep = _base_dep()
    dep["replacement"] = ""
    record = {"lifecycle_status": "DEPRECATED", "deprecation": dep}
    errors = deprecation_errors("legacy_model", record, {}, CHANGES, POLICY)
    assert any("must declare a 'replacement'" in e for e in errors)


def test_removal_before_minimum_window_fails() -> None:
    dep = _base_dep()
    dep["earliest_removal_date"] = "2026-07-25"  # 6 days after start
    record = {"lifecycle_status": "DEPRECATED", "deprecation": dep}
    errors = deprecation_errors("legacy_model", record, {}, CHANGES, POLICY)
    assert any("minimum window" in e for e in errors)


def test_lifecycle_change_without_change_record_fails() -> None:
    dep = _base_dep()
    dep["change_record"] = ""
    record = {"lifecycle_status": "DEPRECATED", "deprecation": dep}
    errors = deprecation_errors("legacy_model", record, {}, CHANGES, POLICY)
    assert any("requires a 'change_record'" in e for e in errors)


def test_change_record_not_found_fails() -> None:
    dep = _base_dep()
    dep["change_record"] = "CHG-does-not-exist"
    record = {"lifecycle_status": "DEPRECATED", "deprecation": dep}
    errors = deprecation_errors("legacy_model", record, {}, CHANGES, POLICY)
    assert any("not found under governance/changes" in e for e in errors)


def test_removed_asset_with_active_consumer_fails() -> None:
    record = {"lifecycle_status": "REMOVED", "deprecation": _base_dep()}
    errors = deprecation_errors("legacy_model", record, CONSUMERS, CHANGES, POLICY)
    assert any("still has active consumers" in e for e in errors)


def test_valid_deprecation_passes() -> None:
    record = {"lifecycle_status": "DEPRECATED", "deprecation": _base_dep()}
    # No active consumers passed -> DEPRECATED (not removed) is allowed.
    assert deprecation_errors("legacy_model", record, {}, CHANGES, POLICY) == []


def test_removal_scheduled_requires_approval() -> None:
    dep = _base_dep()
    dep["removal_approval"] = ""
    record = {"lifecycle_status": "REMOVAL_SCHEDULED", "deprecation": dep}
    errors = deprecation_errors("legacy_model", record, {}, CHANGES, POLICY)
    assert any("removal_approval" in e for e in errors)
