"""Failure-scenario lifecycle CLI (Sprint 6, ADR-013).

Invoked through ``scripts/run_failure_scenario.sh``. Commands:

- ``plan``    — print the scenario spec, affected resources, and gates (safe)
- ``status``  — print gate/approval state without mutating anything (safe)
- ``run``     — authorize and start one scenario (gated)
- ``verify``  — print the scenario's verification queries to execute (safe)
- ``recover`` — print the controlled recovery action and audit template (safe)
- ``cleanup`` — print/emit the scenario cleanup contract (gated telemetry)

``run`` performs the authorization chain and emits structured telemetry, then
prints the exact injection steps for the operator/agent to execute inside the
live game-day window. It never mutates cloud resources by itself: every
mutation is an explicit, logged operator command from the printed plan, which
keeps LOW/MEDIUM/HIGH scenarios reviewable and prevents this CLI from
becoming an unattended destruction engine.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from atlas.failure_injection.framework import (
    APPROVAL_VAR,
    SCENARIO_VAR,
    InjectionRefused,
    authorize_injection,
    is_injection_requested,
)
from atlas.failure_injection.registry import get_scenario, load_catalog, validate_catalog
from atlas.observability.logging import emit_event

SAFE_COMMANDS = frozenset({"plan", "status", "verify", "recover"})
GATED_COMMANDS = frozenset({"run", "cleanup"})


def _print_spec(spec: dict[str, Any]) -> None:
    print(json.dumps(spec, indent=2, default=str))


def _plan(spec: dict[str, Any]) -> int:
    print(f"== PLAN {spec['scenario_id']} ({spec['category']}, risk {spec['risk_level']}) ==")
    _print_spec(spec)
    print("\nAffected resources / target component:")
    print(f"  {spec['target_component']}")
    print("Approvals required before `run`:")
    for approval in spec["approval_required"]:
        print(f"  {approval}=true")
    print(f"Maximum duration: {spec['maximum_duration_minutes']} minutes")
    print(f"Maximum cost: ${spec['maximum_cost_usd']}")
    return 0


def _status(spec: dict[str, Any], environment: str) -> int:
    state = {
        "scenario_id": spec["scenario_id"],
        "environment": environment,
        "scenario_requested": is_injection_requested(),
        "requested_scenario": os.environ.get(SCENARIO_VAR, ""),
        "approvals": {a: os.environ.get(a, "unset") for a in spec["approval_required"]},
        "execution_mode": spec["execution_mode"],
    }
    print(json.dumps(state, indent=2))
    return 0


def _run(spec: dict[str, Any], environment: str, batch_id: str | None) -> int:
    try:
        authorization = authorize_injection(spec["scenario_id"], environment=environment, batch_id=batch_id)
    except InjectionRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(f"== AUTHORIZED {spec['scenario_id']} until {authorization.deadline.isoformat()} ==")
    print("Injection method (execute exactly, inside the game-day window):")
    print(f"  {spec['injection_method']}")
    print("Expected detection:")
    print(f"  {spec['expected_detection']}")
    print("Expected containment:")
    print(f"  {spec['expected_containment']}")
    print("Allowed data impact (anything beyond this aborts the scenario):")
    print(f"  {spec['allowed_data_impact']}")
    return 0


def _verify(spec: dict[str, Any]) -> int:
    print(f"== VERIFY {spec['scenario_id']} ==")
    for query in spec["verification_queries"]:
        print(f"  - {query}")
    return 0


def _recover(spec: dict[str, Any]) -> int:
    print(f"== RECOVER {spec['scenario_id']} ==")
    print(f"Controlled recovery action(s): {spec['recovery_action']}")
    print(
        "Record the attempt in atlas_ops.recovery_actions via "
        "atlas.ops.recovery_actions (SUCCESS requires verification_status=VERIFIED)."
    )
    return 0


def _cleanup(spec: dict[str, Any], environment: str) -> int:
    emit_event(
        "failure_injection_cleanup",
        severity="INFO",
        component="failure_injection",
        check_name=spec["scenario_id"],
        status="CLEANUP",
        environment=environment,
    )
    print(f"== CLEANUP {spec['scenario_id']} ==")
    print(f"  {spec['cleanup']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Atlas controlled failure-scenario lifecycle")
    parser.add_argument("command", choices=sorted(SAFE_COMMANDS | GATED_COMMANDS | {"validate"}))
    parser.add_argument("--scenario", help="explicit scenario id (required for all but validate)")
    parser.add_argument("--environment", help="explicit target environment (required for run/cleanup)")
    parser.add_argument("--batch-id", default=None, help="isolated batch id (atlas-s6- prefix)")
    args = parser.parse_args(argv)

    if args.command == "validate":
        errors = validate_catalog(load_catalog())
        for error in errors:
            print(f"INVALID  {error}", file=sys.stderr)
        print(f"{'INVALID' if errors else 'VALID'}: failure-scenario catalog")
        return 1 if errors else 0

    if not args.scenario:
        parser.error("--scenario is required (fault injection never runs implicitly)")
    spec = get_scenario(args.scenario)

    if args.command in {"run", "cleanup", "status"} and not args.environment:
        parser.error("--environment is required (no implicit environment)")

    if args.command == "plan":
        return _plan(spec)
    if args.command == "status":
        return _status(spec, args.environment)
    if args.command == "run":
        if os.environ.get(APPROVAL_VAR, "").lower() != "true":
            print(f"REFUSED: {APPROVAL_VAR}=true is required", file=sys.stderr)
            return 2
        return _run(spec, args.environment, args.batch_id)
    if args.command == "verify":
        return _verify(spec)
    if args.command == "recover":
        return _recover(spec)
    if args.command == "cleanup":
        return _cleanup(spec, args.environment)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
