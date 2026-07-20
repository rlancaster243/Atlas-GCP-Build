"""Failure-scenario catalog loading and schema validation (ADR-013).

The catalog (``config/failure_scenarios.yaml``) is the single source of truth
for every controlled failure scenario. CI validates the full catalog schema on
every run so a malformed or under-specified scenario can never reach a game
day.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

CATALOG_PATH = Path(__file__).resolve().parents[3] / "config" / "failure_scenarios.yaml"

REQUIRED_FIELDS = (
    "category",
    "description",
    "risk_level",
    "target_component",
    "preconditions",
    "injection_method",
    "expected_detection",
    "expected_alert",
    "expected_containment",
    "allowed_data_impact",
    "recovery_action",
    "verification_queries",
    "cleanup",
    "recurrence_prevention",
    "execution_mode",
)

ALLOWED_CATEGORIES = frozenset(
    {
        "INGESTION",
        "ORCHESTRATION",
        "WAREHOUSE",
        "SCHEMA",
        "IAM",
        "DEPLOYMENT",
        "ROLLBACK",
        "OBSERVABILITY",
        "COST",
    }
)
ALLOWED_RISK_LEVELS = frozenset({"LOW", "MEDIUM", "HIGH"})
ALLOWED_EXECUTION_MODES = frozenset({"unit", "live", "both"})

# Recovery actions must come from the controlled atlas_ops.recovery_actions
# vocabulary; compound values like "QUARANTINE_BATCH then RERUN_BATCH" are
# allowed as long as every referenced action is controlled.
_CONTROLLED_ACTIONS = (
    "RETRY_TASK",
    "RERUN_BATCH",
    "REPAIR_PARTIAL_LOAD",
    "QUARANTINE_BATCH",
    "BACKFILL",
    "RESTORE_RELEASE",
    "FORWARD_MIGRATION",
    "RESTORE_IAM",
    "REBUILD_PARTITION",
    "PAUSE_SCHEDULE",
    "RESUME_SCHEDULE",
    "RECONSTRUCT_AUDIT",
    "RESET_MONITOR",
    "MANUAL_CONTAINMENT",
)


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    """Load and parse the failure-scenario catalog."""
    return yaml.safe_load((path or CATALOG_PATH).read_text(encoding="utf-8"))


def validate_catalog(catalog: dict[str, Any]) -> list[str]:
    """Return every schema violation in the catalog (empty list == valid)."""
    errors: list[str] = []
    scenarios = catalog.get("scenarios")
    if not isinstance(scenarios, dict) or not scenarios:
        return ["catalog has no scenarios mapping"]
    defaults = catalog.get("defaults", {})

    for scenario_id, spec in scenarios.items():
        prefix = f"{scenario_id}: "
        if not scenario_id.startswith("S6-"):
            errors.append(prefix + "scenario id must start with S6-")
        if not isinstance(spec, dict):
            errors.append(prefix + "scenario body must be a mapping")
            continue
        for field in REQUIRED_FIELDS:
            if field not in spec:
                errors.append(prefix + f"missing required field {field!r}")
        category = spec.get("category")
        if category not in ALLOWED_CATEGORIES:
            errors.append(prefix + f"invalid category {category!r}")
        elif category:
            expected_prefixes = {
                "INGESTION": "S6-ING-",
                "ORCHESTRATION": "S6-AIR-",
                "WAREHOUSE": "S6-DBT-",
                "SCHEMA": "S6-SCH-",
                "IAM": "S6-IAM-",
                "DEPLOYMENT": "S6-DEP-",
                "ROLLBACK": "S6-RBK-",
                "OBSERVABILITY": "S6-OBS-",
                "COST": "S6-COST-",
            }
            if not scenario_id.startswith(expected_prefixes[category]):
                errors.append(prefix + f"id prefix does not match category {category}")
        risk = spec.get("risk_level")
        if risk not in ALLOWED_RISK_LEVELS:
            errors.append(prefix + f"invalid risk_level {risk!r} (no CRITICAL scenarios exist)")
        mode = spec.get("execution_mode")
        if mode not in ALLOWED_EXECUTION_MODES:
            errors.append(prefix + f"invalid execution_mode {mode!r}")
        recovery = str(spec.get("recovery_action", ""))
        if recovery and not any(action in recovery for action in _CONTROLLED_ACTIONS):
            errors.append(prefix + f"recovery_action {recovery!r} references no controlled action type")
        approvals = spec.get("approval_required", defaults.get("approval_required", []))
        if "ATLAS_APPROVE_FAILURE_INJECTION" not in approvals:
            errors.append(prefix + "ATLAS_APPROVE_FAILURE_INJECTION must always be required")
        max_cost = spec.get("maximum_cost_usd", defaults.get("maximum_cost_usd"))
        if not isinstance(max_cost, (int, float)) or max_cost > 1.0:
            errors.append(prefix + f"maximum_cost_usd {max_cost!r} missing or above the $1 scenario ceiling")
        max_duration = spec.get("maximum_duration_minutes", defaults.get("maximum_duration_minutes"))
        if not isinstance(max_duration, (int, float)) or max_duration > 120:
            errors.append(prefix + f"maximum_duration_minutes {max_duration!r} missing or above 120")
    return errors


def get_scenario(scenario_id: str, catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return one scenario spec with catalog defaults merged in."""
    catalog = catalog or load_catalog()
    scenarios = catalog.get("scenarios", {})
    if scenario_id not in scenarios:
        raise KeyError(f"unknown failure scenario: {scenario_id}")
    defaults = catalog.get("defaults", {})
    merged = {**defaults, **scenarios[scenario_id], "scenario_id": scenario_id}
    merged.setdefault("approval_required", defaults.get("approval_required", []))
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="Atlas failure-scenario catalog tools")
    parser.add_argument("--validate", action="store_true", help="validate the catalog schema")
    parser.add_argument("--show", metavar="SCENARIO_ID", help="print one merged scenario spec")
    args = parser.parse_args()

    catalog = load_catalog()
    if args.validate:
        errors = validate_catalog(catalog)
        if errors:
            for error in errors:
                print(f"INVALID  {error}")
            return 1
        print(f"VALID  {len(catalog['scenarios'])} scenarios pass schema validation")
        return 0
    if args.show:
        print(json.dumps(get_scenario(args.show, catalog), indent=2, default=str))
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
