"""Schema compatibility checker (Sprint 7, ADR-017).

Compares two schema manifests and classifies every difference into one of four
compatibility classes:

    COMPATIBLE               additive / widening / metadata-only
    CONDITIONALLY_COMPATIBLE requires consumer migration or approved evidence
    BREAKING                 removes/renames/tightens; changes grain/partition/id
    PROHIBITED               unversioned replacement, contract downgrade

A manifest is a JSON document::

    {
      "version": 1,
      "assets": {
        "<asset_id>": {
          "contract_version": "1.0",
          "grain": "one row per event_id",
          "partition_field": "event_date",      # optional
          "event_identity": ["event_id"],         # optional
          "fields": {
            "<name>": {
              "type": "string",
              "nullable": true,
              "accepted_values": ["a", "b"]        # optional
            }
          }
        }
      }
    }

Usage::

    python -m atlas.governance.schema_check --baseline base.json \\
        --candidate cand.json --output report.json
    python -m atlas.governance.schema_check --generate manifest.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from atlas.config.settings import atlas_root

COMPATIBLE = "COMPATIBLE"
CONDITIONALLY_COMPATIBLE = "CONDITIONALLY_COMPATIBLE"
BREAKING = "BREAKING"
PROHIBITED = "PROHIBITED"

# Severity ordering (higher == worse) used to pick the overall class.
_SEVERITY = {
    COMPATIBLE: 0,
    CONDITIONALLY_COMPATIBLE: 1,
    BREAKING: 2,
    PROHIBITED: 3,
}


@dataclass
class Change:
    asset_id: str
    change_type: str
    detail: str
    compatibility_class: str


@dataclass
class CompatibilityReport:
    overall_class: str = COMPATIBLE
    changes: list[Change] = field(default_factory=list)

    def add(self, change: Change) -> None:
        self.changes.append(change)
        if _SEVERITY[change.compatibility_class] > _SEVERITY[self.overall_class]:
            self.overall_class = change.compatibility_class

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_class": self.overall_class,
            "change_count": len(self.changes),
            "changes": [asdict(c) for c in self.changes],
        }


def _version_tuple(v: str) -> tuple[int, int]:
    try:
        major, minor = str(v).split(".")[:2]
        return int(major), int(minor)
    except (ValueError, AttributeError):
        return (0, 0)


def _compare_asset(
    asset_id: str, base: dict[str, Any], cand: dict[str, Any], report: CompatibilityReport
) -> None:
    base_fields = base.get("fields", {}) or {}
    cand_fields = cand.get("fields", {}) or {}
    schema_changed = False

    # Grain / partition / identity — structural, breaking when changed.
    for key, ctype in (
        ("grain", "grain_changed"),
        ("partition_field", "partition_field_changed"),
        ("event_identity", "event_identity_changed"),
    ):
        if base.get(key) is not None and base.get(key) != cand.get(key):
            schema_changed = True
            report.add(
                Change(
                    asset_id,
                    ctype,
                    f"{key}: {base.get(key)!r} -> {cand.get(key)!r}",
                    BREAKING,
                )
            )

    # Removed fields -> BREAKING.
    for name in base_fields:
        if name not in cand_fields:
            schema_changed = True
            report.add(Change(asset_id, "field_removed", f"field '{name}' removed", BREAKING))

    # Added fields -> COMPATIBLE if nullable else CONDITIONALLY_COMPATIBLE.
    for name, spec in cand_fields.items():
        if name not in base_fields:
            schema_changed = True
            nullable = spec.get("nullable", True)
            cls = COMPATIBLE if nullable else CONDITIONALLY_COMPATIBLE
            report.add(
                Change(
                    asset_id,
                    "field_added",
                    f"field '{name}' added (nullable={nullable})",
                    cls,
                )
            )

    # Changed fields.
    for name in base_fields.keys() & cand_fields.keys():
        b = base_fields[name]
        c = cand_fields[name]
        if b.get("type") and c.get("type") and b["type"] != c["type"]:
            schema_changed = True
            report.add(
                Change(
                    asset_id,
                    "type_changed",
                    f"field '{name}' type {b['type']} -> {c['type']}",
                    BREAKING,
                )
            )
        b_nullable = b.get("nullable", True)
        c_nullable = c.get("nullable", True)
        if b_nullable and not c_nullable:
            schema_changed = True
            report.add(
                Change(
                    asset_id,
                    "nullability_tightened",
                    f"field '{name}' nullable -> required",
                    BREAKING,
                )
            )
        elif not b_nullable and c_nullable:
            schema_changed = True
            report.add(
                Change(
                    asset_id,
                    "nullability_loosened",
                    f"field '{name}' required -> nullable",
                    COMPATIBLE,
                )
            )
        b_vals = b.get("accepted_values")
        c_vals = c.get("accepted_values")
        if b_vals is not None and c_vals is not None and set(b_vals) != set(c_vals):
            schema_changed = True
            removed = set(b_vals) - set(c_vals)
            if removed:
                report.add(
                    Change(
                        asset_id,
                        "accepted_values_narrowed",
                        f"field '{name}' drops values {sorted(removed)}",
                        BREAKING,
                    )
                )
            else:
                report.add(
                    Change(
                        asset_id,
                        "accepted_values_widened",
                        f"field '{name}' widens values {sorted(set(c_vals) - set(b_vals))}",
                        COMPATIBLE,
                    )
                )

    # Contract versioning: any schema change with an unchanged or decreased
    # contract version is a PROHIBITED unversioned replacement.
    b_ver = base.get("contract_version", "0.0")
    c_ver = cand.get("contract_version", "0.0")
    if schema_changed:
        if _version_tuple(c_ver) < _version_tuple(b_ver):
            report.add(
                Change(
                    asset_id,
                    "contract_version_downgraded",
                    f"contract_version {b_ver} -> {c_ver}",
                    PROHIBITED,
                )
            )
        elif _version_tuple(c_ver) == _version_tuple(b_ver):
            report.add(
                Change(
                    asset_id,
                    "unversioned_change",
                    f"schema changed but contract_version stayed {b_ver}",
                    PROHIBITED,
                )
            )


def compare_manifests(baseline: dict[str, Any], candidate: dict[str, Any]) -> CompatibilityReport:
    report = CompatibilityReport()
    base_assets = baseline.get("assets", {}) or {}
    cand_assets = candidate.get("assets", {}) or {}
    for asset_id in base_assets:
        if asset_id not in cand_assets:
            report.add(Change(asset_id, "asset_removed", "asset removed from manifest", BREAKING))
            continue
        _compare_asset(asset_id, base_assets[asset_id], cand_assets[asset_id], report)
    # Newly added assets are always compatible.
    for asset_id in cand_assets:
        if asset_id not in base_assets:
            report.add(Change(asset_id, "asset_added", "new asset added", COMPATIBLE))
    return report


# ---------------------------------------------------------------------------
# Manifest generation from repository sources (dbt YAML + governance meta).
# ---------------------------------------------------------------------------

# Structural properties the dbt SQL config expresses that are not in the YAML
# column list; kept as a small explicit map so the manifest captures grain-
# critical attributes without parsing Jinja.
_STRUCTURAL: dict[str, dict[str, Any]] = {
    "fct_events": {"partition_field": "event_date", "event_identity": ["event_id"]},
}


def _dbt_models_dir() -> Path:
    return atlas_root() / "dbt" / "atlas_dbt" / "models"


def generate_manifest() -> dict[str, Any]:
    assets: dict[str, Any] = {}
    for yml in sorted(_dbt_models_dir().glob("*/*.yml")):
        data = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}
        for model in data.get("models", []) or []:
            name = model.get("name")
            if not name:
                continue
            gov = (model.get("meta") or {}).get("governance", {}) or {}
            fields: dict[str, Any] = {}
            for col in model.get("columns", []) or []:
                col_name = col.get("name")
                if not col_name:
                    continue
                tests = col.get("tests", []) or []
                nullable = not any(_is_not_null(t) for t in tests)
                accepted = _extract_accepted_values(tests)
                spec: dict[str, Any] = {
                    "type": col.get("data_type", "unknown"),
                    "nullable": nullable,
                }
                if accepted is not None:
                    spec["accepted_values"] = accepted
                fields[col_name] = spec
            entry: dict[str, Any] = {
                "contract_version": gov.get("contract_version", "0.0"),
                "grain": gov.get("grain", ""),
                "fields": fields,
            }
            entry.update(_STRUCTURAL.get(name, {}))
            assets[name] = entry
    return {"version": 1, "assets": assets}


def _is_not_null(test: Any) -> bool:
    return test == "not_null"


def _extract_accepted_values(tests: list[Any]) -> list[Any] | None:
    for t in tests:
        if isinstance(t, dict) and "accepted_values" in t:
            args = t["accepted_values"].get("arguments", t["accepted_values"])
            return args.get("values") if isinstance(args, dict) else None
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Atlas schema compatibility checker")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--generate", type=Path, help="write a manifest from repo sources")
    parser.add_argument(
        "--fail-on",
        default="BREAKING",
        choices=[COMPATIBLE, CONDITIONALLY_COMPATIBLE, BREAKING, PROHIBITED],
        help="exit non-zero when overall class is at/above this severity",
    )
    args = parser.parse_args(argv)

    if args.generate:
        manifest = generate_manifest()
        args.generate.parent.mkdir(parents=True, exist_ok=True)
        args.generate.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        print(f"manifest written: {len(manifest['assets'])} assets -> {args.generate}")
        return 0

    if not args.baseline or not args.candidate:
        parser.error("--baseline and --candidate are required unless --generate is used")

    baseline = json.loads(args.baseline.read_text())
    candidate = json.loads(args.candidate.read_text())
    report = compare_manifests(baseline, candidate)
    payload = report.to_dict()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))

    if _SEVERITY[report.overall_class] >= _SEVERITY[args.fail_on]:
        print(f"schema check: {report.overall_class} (>= {args.fail_on})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
