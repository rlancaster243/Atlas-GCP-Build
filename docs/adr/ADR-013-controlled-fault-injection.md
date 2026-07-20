# ADR-013: Controlled Fault Injection

Status: Accepted (Sprint 6)

## Context

Sprint 6 must prove that Atlas detects, contains, and recovers from realistic
failures. That requires *causing* failures — in a system whose canonical data,
audit history, and IAM posture must never become collateral damage. An
ungoverned "chaos" switch would be worse than no testing at all.

## Decision

1. **One catalog.** Every injectable failure is declared in
   `config/failure_scenarios.yaml` with a full contract: injection method,
   expected detection/alert/containment, allowed data impact, recovery
   action, verification queries, cleanup, approvals, and hard duration/cost
   ceilings. CI validates the catalog schema (`gate_failure_injection`);
   an under-specified scenario cannot exist.
2. **Disabled by default, explicitly armed.** Activation requires ALL of:
   an explicit scenario id in `ATLAS_INJECTION_SCENARIO`,
   `ATLAS_APPROVE_FAILURE_INJECTION=true`, and every scenario-specific
   approval (`ATLAS_APPROVE_IAM`, `ATLAS_APPROVE_DESTRUCTIVE_FIXTURE`,
   `ATLAS_APPROVE_ROLLBACK_TEST`). A lingering approval variable alone is
   inert; environment inheritance can never arm an injection.
3. **Never scheduled, never canonical, never production.**
   `atlas.failure_injection.framework` refuses scheduled Airflow runs,
   batch ids without the isolated `atlas-s6-` prefix, and any environment
   other than `atlas-dev`. Refusal raises — there is no silent fallback to
   normal execution, and a requested-but-refused injection logs a structured
   `failure_injection_refused` event.
4. **No CRITICAL blast radius.** Risk levels are LOW/MEDIUM/HIGH only; the
   schema has no CRITICAL tier, and destructive operations are restricted to
   isolated fixtures gated by `ATLAS_APPROVE_DESTRUCTIVE_FIXTURE`.
5. **The CLI plans; the operator mutates.** `run_failure_scenario.sh`
   authorizes, emits telemetry, and prints the exact injection steps; cloud
   mutations are explicit logged commands executed inside the game-day
   window, keeping every destructive step reviewable.
6. **Bounded.** Every scenario carries `maximum_duration_minutes` (≤ 120,
   enforced via deadline checks) and `maximum_cost_usd` (≤ $1).

## Consequences

- Drill work is reproducible from Git: the catalog is the runbook's contract.
- Normal pipeline execution is provably injection-free (CI gate + unit tests
  covering default-off, approval, environment, batch, and schedule refusal).
- The framework adds one more approval ceremony per drill; that is the point.
