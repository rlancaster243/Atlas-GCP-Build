"""Load and validate Atlas governance metadata (Sprint 7, ADR-016).

Two authoritative sources are merged into one asset index:

1. dbt models    -> ``meta.governance`` blocks in ``dbt/atlas_dbt/models/**/*.yml``
2. non-dbt assets -> ``governance/non_dbt_assets.yml``

``validate_governance`` returns a list of human-readable error strings; an empty
list means the governance metadata satisfies ``governance/policy.yml``. This is
pure/offline so the governance CI gate needs no credentials.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from atlas.config.settings import atlas_root


class GovernanceError(ValueError):
    """Raised when governance metadata cannot be loaded."""


def governance_dir() -> Path:
    return atlas_root() / "governance"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise GovernanceError(f"missing governance file: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise GovernanceError(f"governance file is not a mapping: {path}")
    return data


def load_policy() -> dict[str, Any]:
    return _load_yaml(governance_dir() / "policy.yml")


def load_non_dbt_assets() -> list[dict[str, Any]]:
    data = _load_yaml(governance_dir() / "non_dbt_assets.yml")
    assets = data.get("assets", [])
    if not isinstance(assets, list):
        raise GovernanceError("non_dbt_assets.yml: 'assets' must be a list")
    return assets


def load_classifications() -> dict[str, Any]:
    return _load_yaml(governance_dir() / "classifications.yml")


def load_retention() -> dict[str, Any]:
    return _load_yaml(governance_dir() / "retention.yml")


def load_consumers() -> dict[str, Any]:
    data = _load_yaml(governance_dir() / "consumers.yml")
    return data.get("consumers", {}) or {}


def _dbt_models_dir() -> Path:
    return atlas_root() / "dbt" / "atlas_dbt" / "models"


def load_dbt_model_governance() -> list[dict[str, Any]]:
    """Extract governance metadata from dbt model ``meta.governance`` blocks.

    Parses the model property YAML files directly (no dbt runtime needed), so
    this works in credentialless CI. Each returned record is normalized into the
    same shape as a non-dbt asset, with ``asset_id`` = the dbt model name and
    ``asset_type`` inferred from the model's directory.
    """
    dir_to_type = {
        "staging": "staging_model",
        "intermediate": "intermediate_model",
        "core": "core_model",  # refined below by name
        "marts": "mart_model",
    }
    records: list[dict[str, Any]] = []
    for yml in sorted(_dbt_models_dir().glob("*/*.yml")):
        layer = yml.parent.name
        data = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}
        for model in data.get("models", []) or []:
            name = model.get("name")
            meta = (model.get("meta") or {}).get("governance")
            if not name or meta is None:
                # Models without governance meta are reported by validation.
                records.append(
                    {
                        "asset_id": name or f"<unnamed in {yml.name}>",
                        "asset_type": dir_to_type.get(layer, "staging_model"),
                        "repository_path": str(yml.relative_to(atlas_root())),
                        "_missing_meta": True,
                        "source": "dbt",
                    }
                )
                continue
            asset_type = dir_to_type.get(layer, "staging_model")
            if layer == "core":
                asset_type = "fact_model" if name.startswith("fct_") else "dimension_model"
            record = dict(meta)
            record["asset_id"] = name
            record["asset_type"] = asset_type
            # dbt `description` is the authoritative purpose text; do not
            # duplicate it inside meta.governance.
            description = (model.get("description") or "").strip()
            if description and not record.get("purpose"):
                record["purpose"] = description
            record.setdefault("repository_path", str(yml.relative_to(atlas_root())))
            record.setdefault("source", str(yml.relative_to(atlas_root())))
            record["_origin"] = "dbt_meta"
            records.append(record)
    return records


def build_asset_index() -> dict[str, dict[str, Any]]:
    """Merge dbt and non-dbt governance records keyed by asset_id."""
    index: dict[str, dict[str, Any]] = {}
    for record in load_dbt_model_governance():
        index[record["asset_id"]] = record
    for asset in load_non_dbt_assets():
        record = dict(asset)
        record["_origin"] = "registry"
        index[record["asset_id"]] = record
    return index


def _is_permanent(retention: dict[str, Any], retention_class: str) -> bool:
    cls = (retention.get("classes", {}) or {}).get(retention_class, {})
    return bool(cls.get("is_permanent_evidence"))


def _change_record_ids() -> set[str]:
    """Change_ids declared under governance/changes/ (excluding the template)."""
    ids: set[str] = set()
    changes_dir = governance_dir() / "changes"
    if not changes_dir.exists():
        return ids
    for path in changes_dir.glob("*.yml"):
        if path.name == "TEMPLATE.yml":
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if data.get("change_id"):
            ids.add(str(data["change_id"]))
    return ids


def _days_between(start: str, end: str) -> int | None:
    from datetime import date

    try:
        s = date.fromisoformat(str(start))
        e = date.fromisoformat(str(end))
    except (ValueError, TypeError):
        return None
    return (e - s).days


def deprecation_errors(
    asset_id: str,
    record: dict[str, Any],
    consumers: dict[str, Any],
    change_ids: set[str],
    policy: dict[str, Any],
) -> list[str]:
    """Validate the deprecation lifecycle for a single asset (pure function)."""
    status = record.get("lifecycle_status")
    if status in (None, "ACTIVE"):
        return []
    errors: list[str] = []
    dep_policy = policy.get("deprecation", {})
    min_window = int(dep_policy.get("minimum_window_days", 30))
    dep = record.get("deprecation") or {}

    if not dep:
        return [f"{asset_id}: lifecycle '{status}' requires a 'deprecation' block"]

    # 1. Replacement required.
    if dep_policy.get("require_replacement", True) and not str(dep.get("replacement", "")).strip():
        errors.append(f"{asset_id}: deprecated/removed asset must declare a 'replacement'")

    # 2. Lifecycle change must cite a change record that exists.
    change_ref = str(dep.get("change_record", "")).strip()
    if dep_policy.get("require_change_record", True):
        if not change_ref:
            errors.append(f"{asset_id}: lifecycle change requires a 'change_record' reference")
        elif change_ref not in change_ids:
            errors.append(f"{asset_id}: change_record '{change_ref}' not found under governance/changes/")

    # 3. Removal date must respect the minimum window.
    start = dep.get("deprecation_start")
    removal = dep.get("earliest_removal_date")
    if start and removal:
        gap = _days_between(start, removal)
        if gap is None:
            errors.append(f"{asset_id}: invalid deprecation dates")
        elif gap < min_window:
            errors.append(
                f"{asset_id}: earliest_removal_date is {gap}d after start (minimum window is {min_window}d)"
            )
    elif status in ("REMOVAL_SCHEDULED", "REMOVED"):
        errors.append(f"{asset_id}: {status} requires deprecation_start and earliest_removal_date")

    # 4. Removal approval required for REMOVAL_SCHEDULED / REMOVED.
    if status in ("REMOVAL_SCHEDULED", "REMOVED") and not str(dep.get("removal_approval", "")).strip():
        errors.append(f"{asset_id}: {status} requires a 'removal_approval'")

    # 5. A REMOVED / REMOVAL_SCHEDULED asset must have no active consumers.
    if status in ("REMOVAL_SCHEDULED", "REMOVED"):
        short = asset_id.split(".")[-1]
        active_readers = []
        for consumer, spec in consumers.items():
            reads = set(spec.get("reads", []) or [])
            if asset_id in reads or short in {r.split(".")[-1] for r in reads}:
                active_readers.append(consumer)
        if active_readers:
            errors.append(
                f"{asset_id}: {status} but still has active consumers "
                f"{sorted(active_readers)} — migrate them first"
            )

    return errors


def validate_governance() -> list[str]:  # noqa: C901 - explicit sequential checks
    """Return a list of governance policy violations (empty == valid)."""
    errors: list[str] = []
    try:
        policy = load_policy()
        classifications = load_classifications()
        retention = load_retention()
        consumers = load_consumers()
        dbt_records = load_dbt_model_governance()
        non_dbt = load_non_dbt_assets()
    except GovernanceError as exc:
        return [str(exc)]

    required = set(policy["required_fields"])
    valid_types = set(policy["asset_types"])
    valid_lifecycle = set(policy["lifecycle_statuses"])
    valid_class = set(policy["classifications"])
    valid_retention = set(policy["retention_classes"])
    owner_pattern = re.compile(policy["owner_rules"]["allowed_owner_pattern"])
    disallow_email = policy["owner_rules"]["disallow_email_addresses"]
    known_consumers = set(consumers)
    # dbt-core layer types map onto the policy's model-type vocabulary.
    type_alias = {
        "staging_model": "staging_model",
        "intermediate_model": "intermediate_model",
        "dimension_model": "dimension_model",
        "fact_model": "fact_model",
        "mart_model": "mart_model",
    }

    # 1. Single source of truth: a dbt model id must not also be a registry id.
    dbt_ids = {r["asset_id"] for r in dbt_records}
    registry_ids = {a.get("asset_id") for a in non_dbt}
    overlap = dbt_ids & registry_ids
    for dup in sorted(overlap):
        errors.append(f"duplicate source of truth: '{dup}' defined in both dbt meta and registry")

    # 2. Per-asset validation across the merged index.
    index = build_asset_index()
    for asset_id, record in sorted(index.items()):
        if record.get("_missing_meta"):
            errors.append(f"{asset_id}: dbt model missing meta.governance block")
            continue
        for field in required:
            value = record.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append(f"{asset_id}: missing required field '{field}'")
        atype = str(record.get("asset_type", ""))
        if atype not in valid_types and type_alias.get(atype) not in valid_types:
            errors.append(f"{asset_id}: invalid asset_type '{atype}'")
        if record.get("classification") not in valid_class:
            errors.append(f"{asset_id}: invalid classification '{record.get('classification')}'")
        if record.get("lifecycle_status") not in valid_lifecycle:
            errors.append(f"{asset_id}: invalid lifecycle_status '{record.get('lifecycle_status')}'")
        rclass = record.get("retention_class")
        if rclass not in valid_retention:
            errors.append(f"{asset_id}: invalid retention_class '{rclass}'")
        owner = record.get("technical_owner")
        if isinstance(owner, str) and owner:
            if disallow_email and "@" in owner:
                errors.append(f"{asset_id}: technical_owner must be a role id, not an email")
            elif not owner_pattern.match(owner):
                errors.append(f"{asset_id}: technical_owner '{owner}' violates owner pattern")
        for consumer in record.get("consumers", []) or []:
            # Consumers may reference other governed assets or the consumer
            # registry; unknown free-text consumers are allowed only if they
            # look like an asset id (contain a '.') — otherwise they must be
            # registered.
            if consumer in known_consumers or "." in consumer or consumer in index:
                continue
            errors.append(f"{asset_id}: unknown consumer '{consumer}' (not in consumers.yml)")

    # 2b. Deprecation lifecycle validation.
    change_ids = _change_record_ids()
    for asset_id, record in sorted(index.items()):
        if record.get("_missing_meta"):
            continue
        errors.extend(deprecation_errors(asset_id, record, consumers, change_ids, policy))

    # 3. Retention permanence invariant.
    for cls_name, cls in (retention.get("classes", {}) or {}).items():
        if cls.get("is_permanent_evidence") and cls.get("expiration_days") is not None:
            errors.append(f"retention class '{cls_name}': permanent evidence cannot have an expiration")

    # 4. Classification completeness: no RESTRICTED asset if policy asserts none.
    if classifications.get("no_restricted_assets_present"):
        for asset_id, record in index.items():
            if record.get("classification") == "RESTRICTED":
                errors.append(f"{asset_id}: RESTRICTED but classifications.yml asserts none present")

    return errors
