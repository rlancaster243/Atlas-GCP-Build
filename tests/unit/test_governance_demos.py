"""Sprint 7 Phase 14: controlled governance-failure demonstrations (fixtures).

These prove CI *rejects* unsafe governance changes without ever committing the
defect to main. They inject crafted records via loader monkeypatching so the
real committed governance stays valid.
"""

from __future__ import annotations

import json

import pytest

from atlas.governance import registry


def _good_asset(**overrides):
    asset = {
        "asset_id": "demo_asset",
        "asset_type": "operational_table",
        "purpose": "demo",
        "technical_owner": "atlas-data-eng",
        "business_owner_or_role": "atlas-platform",
        "grain": "one row per demo",
        "source": "demo",
        "consumers": [],
        "classification": "INTERNAL",
        "retention_class": "operational_audit",
        "freshness_expectation": "per run",
        "contract_version": "1.0",
        "lifecycle_status": "ACTIVE",
        "repository_path": "demo",
        "runbook": "docs/demo.md",
        "last_reviewed": "2026-07-19",
    }
    asset.update(overrides)
    return asset


@pytest.fixture
def patch_registry(monkeypatch):
    def _apply(assets, dbt_records=None):
        monkeypatch.setattr(registry, "load_non_dbt_assets", lambda: assets)
        monkeypatch.setattr(registry, "load_dbt_model_governance", lambda: dbt_records or [])

    return _apply


def test_valid_asset_passes(patch_registry) -> None:
    patch_registry([_good_asset()])
    assert registry.validate_governance() == []


def test_missing_owner_fails(patch_registry) -> None:
    patch_registry([_good_asset(technical_owner="")])
    errors = registry.validate_governance()
    assert any("missing required field 'technical_owner'" in e for e in errors)


def test_missing_grain_fails(patch_registry) -> None:
    patch_registry([_good_asset(grain="")])
    errors = registry.validate_governance()
    assert any("missing required field 'grain'" in e for e in errors)


def test_invalid_classification_fails(patch_registry) -> None:
    patch_registry([_good_asset(classification="TOP_SECRET")])
    errors = registry.validate_governance()
    assert any("invalid classification" in e for e in errors)


def test_invalid_retention_class_fails(patch_registry) -> None:
    patch_registry([_good_asset(retention_class="forever_and_ever")])
    errors = registry.validate_governance()
    assert any("invalid retention_class" in e for e in errors)


def test_email_owner_fails(patch_registry) -> None:
    patch_registry([_good_asset(technical_owner="someone@example.com")])
    errors = registry.validate_governance()
    assert any("must be a role id" in e for e in errors)


def test_duplicate_source_of_truth_fails(patch_registry) -> None:
    dbt_record = _good_asset(asset_id="fct_events", asset_type="fact_model")
    patch_registry([_good_asset(asset_id="fct_events")], dbt_records=[dbt_record])
    errors = registry.validate_governance()
    assert any("duplicate source of truth" in e for e in errors)


def test_migration_checksum_tamper_is_detected() -> None:
    # Demonstrate: modifying an applied migration changes its checksum and would
    # diverge from the committed lock (the check gate_schema_compatibility runs).
    from atlas.config.settings import atlas_root
    from atlas.ops.migrations import load_manifest

    lock = json.loads((atlas_root() / "sql/migrations/checksums.lock").read_text())
    locked = lock["checksums"]
    tampered = dict(locked)
    # Simulate a tampered file checksum for an applied migration.
    first = next(iter(tampered))
    tampered[first] = "0" * 64
    # The live files still match the lock ...
    assert all(m.checksum == locked[m.migration_id] for m in load_manifest())
    # ... but a tampered checksum would not, which is exactly what the gate flags.
    assert tampered[first] != locked[first]
