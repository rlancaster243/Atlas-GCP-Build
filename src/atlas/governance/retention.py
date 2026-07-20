"""Classification & retention validation and disposal planning (Sprint 7, P9).

Offline validation of ``governance/retention.yml`` plus a dry-run planner that
maps assets to their desired expiration. Live lifecycle/expiration changes
require ``ATLAS_APPROVE_RETENTION_MUTATION=true`` and are applied separately —
this module never mutates cloud resources.
"""

from __future__ import annotations

from typing import Any

from atlas.governance.registry import (
    build_asset_index,
    load_policy,
    load_retention,
)

# Non-permanent classes that legitimately retain data indefinitely because it is
# deterministically rebuildable (not disposable evidence).
_REBUILDABLE = {"canonical_warehouse", "raw_landing"}
# Transient classes that MUST declare a disposal (expiration).
_TRANSIENT = {"observability_logs", "temporary_integration", "test_fixture"}


def validate_retention_config() -> list[str]:
    """Return retention-policy violations (empty == valid)."""
    errors: list[str] = []
    retention = load_retention()
    policy = load_policy()
    classes = retention.get("classes", {}) or {}

    # 1. policy.retention_classes must match the retention.yml class keys exactly
    #    (single source of truth — no drift between the two files).
    policy_classes = set(policy.get("retention_classes", []) or [])
    yaml_classes = set(classes)
    if policy_classes != yaml_classes:
        missing = policy_classes - yaml_classes
        extra = yaml_classes - policy_classes
        if missing:
            errors.append(f"retention classes in policy.yml but not retention.yml: {sorted(missing)}")
        if extra:
            errors.append(f"retention classes in retention.yml but not policy.yml: {sorted(extra)}")

    # 2. Per-class consistency.
    for name, cls in classes.items():
        for req in ("description", "retention", "expiration_days", "is_permanent_evidence"):
            if req not in cls:
                errors.append(f"retention class '{name}': missing '{req}'")
        permanent = bool(cls.get("is_permanent_evidence"))
        expiration = cls.get("expiration_days")
        # Conflict: permanent evidence cannot expire.
        if permanent and expiration is not None:
            errors.append(f"retention class '{name}': permanent evidence cannot have an expiration")
        # Conflict: transient class must declare a disposal window.
        if name in _TRANSIENT and (expiration is None):
            errors.append(f"retention class '{name}': transient class must set expiration_days")
        # Conflict: a non-permanent, non-rebuildable, non-transient class with no
        # disposal is ambiguous.
        if not permanent and name not in _REBUILDABLE and name not in _TRANSIENT and expiration is None:
            errors.append(f"retention class '{name}': ambiguous — declare expiration or permanence")

    return errors


def desired_expiration_days(retention_class: str) -> int | None:
    classes = load_retention().get("classes", {}) or {}
    return classes.get(retention_class, {}).get("expiration_days")


def plan_expirations() -> list[dict[str, Any]]:
    """Dry-run: map each governed asset to its desired expiration disposition.

    Returns records without touching any cloud resource. Permanent audit and
    release evidence are explicitly flagged as ``keep_forever`` so a live applier
    can assert it never expires them.
    """
    retention = load_retention().get("classes", {}) or {}
    plan: list[dict[str, Any]] = []
    for asset_id, record in sorted(build_asset_index().items()):
        if record.get("_missing_meta"):
            continue
        rclass = record.get("retention_class")
        cls = retention.get(rclass, {})
        exp = cls.get("expiration_days")
        permanent = bool(cls.get("is_permanent_evidence"))
        plan.append(
            {
                "asset_id": asset_id,
                "asset_type": record.get("asset_type"),
                "retention_class": rclass,
                "expiration_days": exp,
                "disposition": "keep_forever" if permanent or exp is None else f"expire_{exp}d",
                "is_permanent_evidence": permanent,
            }
        )
    return plan
