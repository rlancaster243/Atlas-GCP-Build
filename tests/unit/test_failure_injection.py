"""Fault-injection framework safety tests (Sprint 6, Phases 3/16)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from atlas.failure_injection.framework import (
    APPROVAL_VAR,
    SCENARIO_VAR,
    InjectionRefused,
    authorize_injection,
    enforce_deadline,
    injection_active_for,
    is_injection_requested,
)
from atlas.failure_injection.registry import (
    ALLOWED_RISK_LEVELS,
    get_scenario,
    load_catalog,
    validate_catalog,
)

CATALOG = load_catalog()


def _env(**overrides: str) -> dict[str, str]:
    base = {
        SCENARIO_VAR: "S6-ING-001",
        APPROVAL_VAR: "true",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------- catalog


def test_catalog_schema_is_valid() -> None:
    assert validate_catalog(CATALOG) == []


def test_no_critical_risk_scenarios_exist() -> None:
    assert "CRITICAL" not in ALLOWED_RISK_LEVELS
    for spec in CATALOG["scenarios"].values():
        assert spec["risk_level"] in ALLOWED_RISK_LEVELS


def test_every_scenario_requires_injection_approval() -> None:
    defaults = CATALOG["defaults"]["approval_required"]
    for scenario_id, spec in CATALOG["scenarios"].items():
        approvals = spec.get("approval_required", defaults)
        assert APPROVAL_VAR in approvals, scenario_id


def test_destructive_scenarios_require_destructive_fixture_approval() -> None:
    for scenario_id in ("S6-ING-004", "S6-DBT-006", "S6-DBT-007"):
        spec = get_scenario(scenario_id, CATALOG)
        assert "ATLAS_APPROVE_DESTRUCTIVE_FIXTURE" in spec["approval_required"]


def test_iam_scenarios_require_iam_approval() -> None:
    for scenario_id in ("S6-IAM-001", "S6-IAM-002", "S6-IAM-003", "S6-IAM-005"):
        spec = get_scenario(scenario_id, CATALOG)
        assert "ATLAS_APPROVE_IAM" in spec["approval_required"]


def test_unknown_scenario_rejected() -> None:
    with pytest.raises(KeyError, match="unknown failure scenario"):
        get_scenario("S6-NOPE-999", CATALOG)


# ---------------------------------------------------------------- activation


def test_disabled_by_default_empty_environment() -> None:
    assert is_injection_requested(env={}) is False
    assert injection_active_for("S6-ING-001", env={}) is False


def test_approval_alone_never_activates_injection() -> None:
    """A lingering approval variable without the explicit scenario is inert."""
    env = {APPROVAL_VAR: "true"}
    assert is_injection_requested(env=env) is False
    assert injection_active_for("S6-ING-001", env=env) is False


def test_scenario_without_approval_is_refused() -> None:
    with pytest.raises(InjectionRefused, match="missing approval"):
        authorize_injection("S6-ING-001", environment="atlas-dev", env=_env(**{APPROVAL_VAR: ""}))


def test_scenario_env_var_must_match_requested_scenario() -> None:
    with pytest.raises(InjectionRefused, match="must explicitly name"):
        authorize_injection(
            "S6-ING-002",
            environment="atlas-dev",
            env=_env(),  # env names S6-ING-001
        )


def test_production_style_environment_refused() -> None:
    for environment in ("atlas-prod", "production", "prod-us"):
        with pytest.raises(InjectionRefused, match="not injectable"):
            authorize_injection("S6-ING-001", environment=environment, env=_env())


def test_scheduled_execution_refused() -> None:
    with pytest.raises(InjectionRefused, match="refuses scheduled execution"):
        authorize_injection(
            "S6-ING-001",
            environment="atlas-dev",
            env=_env(AIRFLOW_CTX_DAG_RUN_TYPE="scheduled"),
        )
    with pytest.raises(InjectionRefused, match="refuses scheduled run ids"):
        authorize_injection(
            "S6-ING-001",
            environment="atlas-dev",
            env=_env(AIRFLOW_CTX_DAG_RUN_ID="scheduled__2026-07-19T00:00:00+00:00"),
        )


def test_canonical_batch_ids_refused() -> None:
    for batch_id in ("atlas-20260719", "atlas-smoke-abc123-run", "atlas-drillb-20260719"):
        with pytest.raises(InjectionRefused, match="not isolated"):
            authorize_injection("S6-ING-001", environment="atlas-dev", batch_id=batch_id, env=_env())


def test_isolated_batch_id_accepted_with_full_approvals() -> None:
    authorization = authorize_injection(
        "S6-ING-001", environment="atlas-dev", batch_id="atlas-s6-ing001-20260719", env=_env()
    )
    assert authorization.scenario_id == "S6-ING-001"
    assert authorization.deadline > datetime.now(tz=UTC)


def test_scenario_specific_approvals_enforced() -> None:
    env = _env(**{SCENARIO_VAR: "S6-ING-004"})
    with pytest.raises(InjectionRefused, match="ATLAS_APPROVE_DESTRUCTIVE_FIXTURE"):
        authorize_injection("S6-ING-004", environment="atlas-dev", env=env)
    env["ATLAS_APPROVE_DESTRUCTIVE_FIXTURE"] = "true"
    authorization = authorize_injection(
        "S6-ING-004", environment="atlas-dev", batch_id="atlas-s6-ing004-x", env=env
    )
    assert authorization.spec["risk_level"] == "HIGH"


def test_timeout_enforcement() -> None:
    authorization = authorize_injection(
        "S6-ING-001", environment="atlas-dev", batch_id="atlas-s6-a", env=_env()
    )
    enforce_deadline(authorization)  # within budget: no raise
    expired = type(authorization)(
        scenario_id=authorization.scenario_id,
        environment=authorization.environment,
        batch_id=authorization.batch_id,
        deadline=datetime.now(tz=UTC) - timedelta(seconds=1),
        spec=authorization.spec,
    )
    with pytest.raises(InjectionRefused, match="exceeded maximum_duration"):
        enforce_deadline(expired)


def test_refused_hook_logs_and_returns_false(capsys: pytest.CaptureFixture[str]) -> None:
    """A requested-but-unapproved scenario is refused loudly, not silently."""
    env = {SCENARIO_VAR: "S6-ING-001"}  # approval missing
    assert injection_active_for("S6-ING-001", env=env) is False
    assert "failure_injection_refused" in capsys.readouterr().out
