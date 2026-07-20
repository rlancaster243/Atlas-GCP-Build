# Extension Points

**Status:** CURRENT · **Audience:** engineer, agent. How to extend Atlas safely.
Sprint 8 **documents** these; it does not implement them. For each: supported use
case, files likely affected, invariants that must remain true, required tests,
required documentation, required evidence, rollback considerations, and the
common unsafe shortcut. Always follow the
[agent-task-protocol.md](../handoff/agent-task-protocol.md).

| Extension | Files likely affected | Invariants to keep | Tests | Unsafe shortcut to avoid |
| --- | --- | --- | --- | --- |
| New batch source | `src/atlas/generator|ingestion`, `sources.yml`, `config/atlas.yaml` | D1, D2, D6, G1–G3 | ingestion + reconciliation | reusing `event_id` semantics blindly |
| API ingestion source | new `src/atlas/ingestion/<api>.py`, source YAML, governance asset | D1, D2, D6, L1 | ingestion unit + contract | calling the API inside PR CI (breaks L1 credentialless) |
| New dbt model | `dbt/atlas_dbt/models/**`, model YAML `meta.governance` | G1–G4, D6 | dbt tests + `gate_governance` | omitting `meta.governance` (fails gate) |
| New fact | `models/core`, `core.yml`, baseline manifest | D5, G3–G5 | uniqueness + reconciliation | changing an existing fact grain |
| New dimension | `models/core`, `core.yml` | G1–G3 | dbt tests | many-to-many join inflating fact |
| New mart | `models/marts`, `marts.yml`, `consumers.yml` | G1–G3, lineage | dbt tests + `gate_lineage_impact` | reading raw directly, skipping layers |
| New data-quality check | dbt tests / `assert_*`, `config/anomaly_profile.yaml` | D6, D7 | the check itself | asserting post-global-dedup for batch anomalies (INC-S6-001) |
| New Airflow task | `dags/`, `src/atlas/batch`, `atlas_step_runner.py` | O1–O2, L4 | `dag_import` + airflow tests | task without audit/telemetry emission |
| New alert | `observability/alerts/*.json`, `config/observability.yaml`, runbook | O6 | `observability_config` + `gate_reference_handoff` | alert with no runbook mapping (breaks O6) |
| New recovery action | `src/atlas/ops`, `recovery_actions` migration | O3 | `test_recovery_actions.py` | marking SUCCESS without VERIFIED |
| New failure scenario | `config/failure_scenarios.yaml`, `src/atlas/failure_injection` | O4 | `test_failure_injection.py` | enabling injection by default |
| New governance asset | `governance/non_dbt_assets.yml` or dbt `meta` | G1–G3 | `gate_governance` | duplicating an asset in two sources (breaks G1) |
| New schema version | `sql/migrations/NNN_*.sql`, `checksums.lock`, baseline | D8, G4–G5 | `gate_schema_compatibility` | editing an applied migration (breaks D8) |
| New environment | `config/cost_controls.yaml`, deploy config | L1–L7, O5 | `gate_performance_cost` | copying prod creds into CI |
| Future event-driven pipeline | new module + ADR | D1–D8 preserved for batch | new + regression | replacing batch semantics without an ADR |

## Rules for every extension

1. Required **documentation**: update the relevant reference doc + an ADR if a
   real decision is made.
2. Required **evidence**: add to the [evidence index](evidence-index.md) with the
   correct live/static/blocked status.
3. Required **rollback**: state how to revert; for schema, only additive/rollback-
   eligible changes without a migration+approval.
4. Confirm **no invariant** (see [architecture-invariants.md](architecture-invariants.md))
   is silently broken; run `bash scripts/validate_ci.sh --mode static`.

A worked example for **API ingestion** is the independent-handoff assignment
(item 12) — see [independent-handoff-assignment.md](../handoff/independent-handoff-assignment.md).
