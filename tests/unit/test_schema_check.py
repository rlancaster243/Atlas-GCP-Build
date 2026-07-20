"""Sprint 7 Phase 4: schema compatibility checker classification tests."""

from __future__ import annotations

import copy

from atlas.governance import schema_check as sc


def _baseline() -> dict:
    return {
        "version": 1,
        "assets": {
            "fct_events": {
                "contract_version": "1.0",
                "grain": "one row per event_id",
                "partition_field": "event_date",
                "event_identity": ["event_id"],
                "fields": {
                    "event_id": {"type": "string", "nullable": False},
                    "user_id": {"type": "string", "nullable": False},
                    "platform": {
                        "type": "string",
                        "nullable": False,
                        "accepted_values": ["ios", "android", "web"],
                    },
                },
            }
        },
    }


def test_identical_manifests_are_compatible() -> None:
    report = sc.compare_manifests(_baseline(), _baseline())
    assert report.overall_class == sc.COMPATIBLE
    assert report.changes == []


def test_added_nullable_field_is_compatible() -> None:
    cand = _baseline()
    cand["assets"]["fct_events"]["fields"]["app_version"] = {"type": "string", "nullable": True}
    cand["assets"]["fct_events"]["contract_version"] = "1.1"
    report = sc.compare_manifests(_baseline(), cand)
    assert report.overall_class == sc.COMPATIBLE
    assert any(c.change_type == "field_added" for c in report.changes)


def test_added_required_field_is_conditionally_compatible() -> None:
    cand = _baseline()
    cand["assets"]["fct_events"]["fields"]["tenant_id"] = {"type": "string", "nullable": False}
    cand["assets"]["fct_events"]["contract_version"] = "1.1"
    report = sc.compare_manifests(_baseline(), cand)
    assert report.overall_class == sc.CONDITIONALLY_COMPATIBLE


def test_removed_field_is_breaking() -> None:
    cand = _baseline()
    del cand["assets"]["fct_events"]["fields"]["user_id"]
    cand["assets"]["fct_events"]["contract_version"] = "2.0"
    report = sc.compare_manifests(_baseline(), cand)
    assert report.overall_class == sc.BREAKING
    assert any(c.change_type == "field_removed" for c in report.changes)


def test_type_change_is_breaking() -> None:
    cand = _baseline()
    cand["assets"]["fct_events"]["fields"]["user_id"]["type"] = "int64"
    cand["assets"]["fct_events"]["contract_version"] = "2.0"
    report = sc.compare_manifests(_baseline(), cand)
    assert report.overall_class == sc.BREAKING
    assert any(c.change_type == "type_changed" for c in report.changes)


def test_grain_change_is_breaking() -> None:
    cand = _baseline()
    cand["assets"]["fct_events"]["grain"] = "one row per (event_id, event_date)"
    cand["assets"]["fct_events"]["contract_version"] = "2.0"
    report = sc.compare_manifests(_baseline(), cand)
    assert report.overall_class == sc.BREAKING
    assert any(c.change_type == "grain_changed" for c in report.changes)


def test_partition_change_is_breaking() -> None:
    cand = _baseline()
    cand["assets"]["fct_events"]["partition_field"] = "ingested_date"
    cand["assets"]["fct_events"]["contract_version"] = "2.0"
    report = sc.compare_manifests(_baseline(), cand)
    assert any(c.change_type == "partition_field_changed" for c in report.changes)


def test_narrowed_enum_is_breaking() -> None:
    cand = _baseline()
    cand["assets"]["fct_events"]["fields"]["platform"]["accepted_values"] = ["ios", "android"]
    cand["assets"]["fct_events"]["contract_version"] = "2.0"
    report = sc.compare_manifests(_baseline(), cand)
    assert any(c.change_type == "accepted_values_narrowed" for c in report.changes)


def test_widened_enum_is_compatible() -> None:
    cand = _baseline()
    cand["assets"]["fct_events"]["fields"]["platform"]["accepted_values"] = [
        "ios",
        "android",
        "web",
        "desktop",
    ]
    cand["assets"]["fct_events"]["contract_version"] = "1.1"
    report = sc.compare_manifests(_baseline(), cand)
    assert report.overall_class == sc.COMPATIBLE
    assert any(c.change_type == "accepted_values_widened" for c in report.changes)


def test_unversioned_change_is_prohibited() -> None:
    cand = _baseline()
    cand["assets"]["fct_events"]["fields"]["app_version"] = {"type": "string", "nullable": True}
    # contract_version left at 1.0 despite the schema change.
    report = sc.compare_manifests(_baseline(), cand)
    assert report.overall_class == sc.PROHIBITED
    assert any(c.change_type == "unversioned_change" for c in report.changes)


def test_contract_downgrade_is_prohibited() -> None:
    cand = _baseline()
    cand["assets"]["fct_events"]["fields"]["app_version"] = {"type": "string", "nullable": True}
    cand["assets"]["fct_events"]["contract_version"] = "0.9"
    report = sc.compare_manifests(_baseline(), cand)
    assert report.overall_class == sc.PROHIBITED


def test_generated_manifest_matches_committed_baseline() -> None:
    # The committed baseline must equal a fresh generation (drift guard).
    import json

    from atlas.config.settings import atlas_root

    committed = json.loads((atlas_root() / "governance/schemas/manifests/baseline.json").read_text())
    fresh = sc.generate_manifest()
    assert committed == fresh, "baseline manifest is stale; regenerate with --generate"


def test_new_asset_is_compatible() -> None:
    cand = copy.deepcopy(_baseline())
    cand["assets"]["new_model"] = {"contract_version": "1.0", "grain": "x", "fields": {}}
    report = sc.compare_manifests(_baseline(), cand)
    assert report.overall_class == sc.COMPATIBLE
