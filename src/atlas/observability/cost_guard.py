"""Cost-guard CLI + control loading (Sprint 7, ADR-020).

Extends the Sprint 6 guards (`atlas.observability.cost_guards`) with a
config-driven estimator and static checks.

Usage::

    python -m atlas.observability.cost_guard estimate \\
        --sql-file q.sql --project <p> --location US [--environment atlas-dev]
    python -m atlas.observability.cost_guard check-partition-filter \\
        --sql-file q.sql [--asset atlas_raw.events]

`estimate` always dry-runs first (bills $0), reports estimated bytes, compares
with the environment threshold, and refuses over-limit execution unless an
explicit approved override is provided. It never executes on estimation failure.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from atlas.config.settings import atlas_root
from atlas.observability.cost_guards import CostGuardViolation

CONTROLS_PATH = "config/cost_controls.yaml"
OVERRIDE_VAR = "ATLAS_APPROVE_COST_OVERRIDE"
SUITE_BYTES_ENV = "ATLAS_MAX_PERFORMANCE_TEST_BYTES"


def load_cost_controls() -> dict[str, Any]:
    path = atlas_root() / CONTROLS_PATH
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def environment_controls(environment: str = "atlas-dev") -> dict[str, Any]:
    controls = load_cost_controls()
    envs = controls.get("environments", {})
    if environment not in envs:
        raise CostGuardViolation(f"unknown cost-control environment '{environment}'")
    return envs[environment]


def max_query_bytes(environment: str = "atlas-dev") -> int:
    return int(environment_controls(environment)["max_query_bytes"])


def max_performance_suite_bytes(environment: str = "atlas-dev") -> int:
    override = os.environ.get(SUITE_BYTES_ENV)
    if override and override.strip().isdigit():
        return int(override)
    return int(environment_controls(environment)["max_performance_suite_bytes"])


# A "partition filter" is a WHERE/AND predicate on a partition column. Kept
# deliberately simple and offline for the static check.
_PARTITION_COLS = ("event_date", "_partitiondate", "_partitiontime", "processing_date")


def has_partition_filter(sql: str) -> bool:
    lowered = sql.lower()
    if "where" not in lowered:
        return False
    return any(re.search(rf"\b{col}\b", lowered) for col in _PARTITION_COLS)


def check_partition_filter(sql: str, asset: str | None, environment: str = "atlas-dev") -> None:
    controls = environment_controls(environment)
    required = set(controls.get("require_partition_filter_assets", []) or [])
    asset_requires = (
        asset in required
        if asset
        else bool(
            re.search(r"\b(atlas_raw\.events|atlas_core\.fct_events|fct_events|`?events`?)\b", sql.lower())
        )
    )
    if asset_requires and not has_partition_filter(sql):
        raise CostGuardViolation(
            f"query over {asset or 'a partitioned asset'} is missing a required "
            "partition filter (event_date/processing_date)"
        )


def estimate(
    sql: str,
    project: str,
    location: str,
    environment: str = "atlas-dev",
    allow_override: bool = False,
) -> dict[str, Any]:
    """Dry-run estimate + threshold enforcement. Returns structured evidence."""
    from google.cloud import bigquery  # imported lazily so static tests need no cloud

    client = bigquery.Client(project=project, location=location)
    job = client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
    estimated = int(job.total_bytes_processed or 0)
    ceiling = max_query_bytes(environment)
    override = allow_override or os.environ.get(OVERRIDE_VAR, "").lower() == "true"
    evidence = {
        "estimated_bytes": estimated,
        "ceiling_bytes": ceiling,
        "environment": environment,
        "within_ceiling": estimated <= ceiling,
        "override_applied": override and estimated > ceiling,
        "location": location,
        "project": project,
    }
    if estimated > ceiling and not override:
        evidence["decision"] = "BLOCKED"
        print(json.dumps(evidence, indent=2))
        raise CostGuardViolation(
            f"estimate {estimated} bytes exceeds ceiling {ceiling} bytes for '{environment}'; "
            f"set {OVERRIDE_VAR}=true only after a documented cost review"
        )
    evidence["decision"] = "ALLOW"
    return evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Atlas cost guard")
    sub = parser.add_subparsers(dest="command", required=True)

    est = sub.add_parser("estimate")
    est.add_argument("--sql-file", type=Path, required=True)
    est.add_argument("--project", required=True)
    est.add_argument("--location", default="US")
    est.add_argument("--environment", default="atlas-dev")
    est.add_argument("--allow-override", action="store_true")

    pf = sub.add_parser("check-partition-filter")
    pf.add_argument("--sql-file", type=Path, required=True)
    pf.add_argument("--asset")
    pf.add_argument("--environment", default="atlas-dev")

    args = parser.parse_args(argv)
    sql = args.sql_file.read_text(encoding="utf-8")

    try:
        if args.command == "estimate":
            evidence = estimate(
                sql,
                args.project,
                args.location,
                args.environment,
                args.allow_override,
            )
            print(json.dumps(evidence, indent=2))
            return 0
        if args.command == "check-partition-filter":
            check_partition_filter(sql, args.asset, args.environment)
            print("partition filter present or not required")
            return 0
    except CostGuardViolation as exc:
        print(f"COST GUARD: {exc}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
