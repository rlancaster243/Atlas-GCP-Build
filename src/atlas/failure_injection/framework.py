"""Fault-injection activation guards (Sprint 6, ADR-013).

Safety contract, enforced here and regression-tested in CI:

- **Disabled by default.** Injection activates only when an explicit scenario
  id is supplied AND ``ATLAS_APPROVE_FAILURE_INJECTION=true`` AND every
  scenario-specific approval variable is true.
- **Never scheduled.** Activation is refused inside scheduled Airflow runs;
  only manually triggered runs may carry a drill.
- **Never canonical.** Batch ids must carry the isolated ``atlas-s6-`` prefix;
  canonical and smoke batch identities are refused.
- **Never production-like.** Only the approved development environment is
  injectable.
- **Never inherited.** Activation requires the explicit
  ``ATLAS_INJECTION_SCENARIO`` parameter naming the scenario; a lingering
  approval variable alone can never activate an injection.
- **Bounded.** Every scenario carries a maximum duration; ``deadline`` turns
  it into an absolute timeout.

There is no fallback path: a refused injection raises ``InjectionRefused``
and the caller must stop. Injection helpers never degrade into normal
execution silently.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from atlas.failure_injection.registry import get_scenario
from atlas.observability.logging import emit_event

APPROVAL_VAR = "ATLAS_APPROVE_FAILURE_INJECTION"
SCENARIO_VAR = "ATLAS_INJECTION_SCENARIO"
ISOLATED_BATCH_PREFIX = "atlas-s6-"

INJECTABLE_ENVIRONMENTS = frozenset({"atlas-dev"})
_PRODUCTION_MARKERS = ("prod", "production")


class InjectionRefused(RuntimeError):
    """A fault-injection request failed the safety gates."""


@dataclass(frozen=True)
class InjectionAuthorization:
    """Proof that one scenario passed every activation gate."""

    scenario_id: str
    environment: str
    batch_id: str | None
    deadline: datetime
    spec: dict[str, Any]


def _is_true(value: str | None) -> bool:
    return (value or "").strip().lower() == "true"


def is_injection_requested(env: dict[str, str] | None = None) -> bool:
    """True only when an explicit scenario parameter is present."""
    env = env if env is not None else dict(os.environ)
    return bool(env.get(SCENARIO_VAR, "").strip())


def authorize_injection(
    scenario_id: str,
    *,
    environment: str,
    batch_id: str | None = None,
    env: dict[str, str] | None = None,
    catalog: dict[str, Any] | None = None,
) -> InjectionAuthorization:
    """Validate every activation gate for one scenario or raise InjectionRefused."""
    env = env if env is not None else dict(os.environ)
    spec = get_scenario(scenario_id, catalog)

    requested = env.get(SCENARIO_VAR, "").strip()
    if requested != scenario_id:
        raise InjectionRefused(
            f"{SCENARIO_VAR} must explicitly name {scenario_id!r} (got {requested!r}); "
            "fault injection never activates through environment inheritance"
        )

    for approval in spec["approval_required"]:
        if not _is_true(env.get(approval)):
            raise InjectionRefused(f"missing approval: {approval}=true is required for {scenario_id}")

    if environment not in INJECTABLE_ENVIRONMENTS or any(
        m in environment.lower() for m in _PRODUCTION_MARKERS
    ):
        raise InjectionRefused(
            f"environment {environment!r} is not injectable (allowed: {sorted(INJECTABLE_ENVIRONMENTS)})"
        )

    run_type = env.get("AIRFLOW_CTX_DAG_RUN_TYPE", "").lower()
    if run_type == "scheduled":
        raise InjectionRefused("fault injection refuses scheduled execution; trigger manually")
    run_id = env.get("AIRFLOW_CTX_DAG_RUN_ID", "")
    if run_id.startswith("scheduled__"):
        raise InjectionRefused("fault injection refuses scheduled run ids")

    if batch_id is not None and not batch_id.startswith(ISOLATED_BATCH_PREFIX):
        raise InjectionRefused(
            f"batch_id {batch_id!r} is not isolated; injection requires the "
            f"{ISOLATED_BATCH_PREFIX!r} prefix and refuses canonical batch ids"
        )

    deadline = datetime.now(tz=UTC) + timedelta(minutes=float(spec["maximum_duration_minutes"]))
    authorization = InjectionAuthorization(
        scenario_id=scenario_id,
        environment=environment,
        batch_id=batch_id,
        deadline=deadline,
        spec=spec,
    )
    emit_event(
        "failure_injection_authorized",
        severity="WARNING",
        component="failure_injection",
        batch_id=batch_id,
        check_name=scenario_id,
        status="AUTHORIZED",
        environment=environment,
    )
    return authorization


def enforce_deadline(authorization: InjectionAuthorization) -> None:
    """Raise when a scenario has exceeded its maximum duration."""
    if datetime.now(tz=UTC) > authorization.deadline:
        emit_event(
            "failure_injection_timeout",
            severity="ERROR",
            component="failure_injection",
            check_name=authorization.scenario_id,
            status="TIMEOUT",
        )
        raise InjectionRefused(
            f"{authorization.scenario_id} exceeded maximum_duration; abort and run cleanup"
        )


def injection_active_for(
    scenario_id: str,
    *,
    batch_id: str | None = None,
    env: dict[str, str] | None = None,
) -> bool:
    """Cheap hook check used inside pipeline code paths.

    Returns True only when the full authorization chain passes. Any refusal
    returns False — a hook can never break a normal (non-drill) run — but the
    refusal is NOT silent when a scenario was explicitly requested: that
    misconfiguration is logged before returning False.
    """
    env = env if env is not None else dict(os.environ)
    if env.get(SCENARIO_VAR, "").strip() != scenario_id:
        return False
    try:
        authorize_injection(
            scenario_id,
            environment=env.get("ATLAS_ENVIRONMENT", "atlas-dev"),
            batch_id=batch_id,
            env=env,
        )
        return True
    except InjectionRefused as exc:
        emit_event(
            "failure_injection_refused",
            severity="ERROR",
            component="failure_injection",
            check_name=scenario_id,
            status="REFUSED",
            error_type="InjectionRefused",
            error_message=str(exc),
        )
        return False
