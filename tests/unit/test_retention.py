"""Sprint 7 Phase 9: classification & retention validation tests."""

from __future__ import annotations

from atlas.governance import retention


def test_live_retention_config_is_valid() -> None:
    assert retention.validate_retention_config() == []


def test_permanent_audit_has_no_expiration() -> None:
    assert retention.desired_expiration_days("operational_audit") is None
    assert retention.desired_expiration_days("release_evidence") is None


def test_transient_classes_have_expiration() -> None:
    assert retention.desired_expiration_days("temporary_integration") is not None
    assert retention.desired_expiration_days("observability_logs") == 30


def test_plan_marks_permanent_evidence_keep_forever() -> None:
    plan = {p["asset_id"]: p for p in retention.plan_expirations()}
    # Operational audit tables must be keep_forever (never expired).
    audit = plan["atlas_ops.pipeline_runs"]
    assert audit["disposition"] == "keep_forever"
    assert audit["is_permanent_evidence"] is True


def test_plan_release_bundles_retained() -> None:
    plan = {p["asset_id"]: p for p in retention.plan_expirations()}
    bundles = plan["gcs://atlas-deployments-example-gcp-project"]
    assert bundles["disposition"] == "keep_forever"


def test_conflicting_permanent_expiration_fails(monkeypatch) -> None:
    bad = {
        "classes": {
            "operational_audit": {
                "description": "x",
                "retention": "indefinite",
                "expiration_days": 7,  # conflict: permanent + expiration
                "is_permanent_evidence": True,
            }
        }
    }
    monkeypatch.setattr(retention, "load_retention", lambda: bad)
    monkeypatch.setattr(retention, "load_policy", lambda: {"retention_classes": ["operational_audit"]})
    errors = retention.validate_retention_config()
    assert any("permanent evidence cannot have an expiration" in e for e in errors)


def test_transient_without_expiration_fails(monkeypatch) -> None:
    bad = {
        "classes": {
            "temporary_integration": {
                "description": "x",
                "retention": "short",
                "expiration_days": None,  # conflict: transient must expire
                "is_permanent_evidence": False,
            }
        }
    }
    monkeypatch.setattr(retention, "load_retention", lambda: bad)
    monkeypatch.setattr(retention, "load_policy", lambda: {"retention_classes": ["temporary_integration"]})
    errors = retention.validate_retention_config()
    assert any("transient class must set expiration_days" in e for e in errors)


def test_policy_retention_class_drift_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        retention,
        "load_retention",
        lambda: {
            "classes": {
                "canonical_warehouse": {
                    "description": "x",
                    "retention": "y",
                    "expiration_days": None,
                    "is_permanent_evidence": False,
                }
            }
        },
    )
    monkeypatch.setattr(
        retention, "load_policy", lambda: {"retention_classes": ["canonical_warehouse", "raw_landing"]}
    )
    errors = retention.validate_retention_config()
    assert any("but not retention.yml" in e for e in errors)
