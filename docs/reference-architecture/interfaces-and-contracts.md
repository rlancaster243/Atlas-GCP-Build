# Interfaces and Contracts

**Status:** CURRENT · **Audience:** engineer, agent. The stable boundaries a
change must respect. Authoritative detail lives in the linked sources; this is
the index of interfaces and where each is enforced.

| Interface | Where defined | Enforced by | Notes |
| --- | --- | --- | --- |
| Event schema | `config/atlas.yaml`, `src/atlas/generator` | generator tests | Atlas-specific (AC-01) |
| File format (JSONL) | `src/atlas/ingestion` | ingestion tests | one event per line, immutable |
| Storage paths | `src/atlas/ingestion`, loader | create-only upload | run-scoped, immutable (INV-D1) |
| Raw-table schema | `sql/` DDL, `atlas_raw.events` | `sql_migrations` gate | partitioned/clustered |
| dbt source boundary | `dbt/atlas_dbt/models/sources/sources.yml` | dbt parse + source tests | raw→dbt contract |
| Transformation contracts | dbt model YAML `contract`/tests | `dbt_static`, `gate_governance` | per-model |
| Orchestration command interface | `scripts/run_atlas_step.sh`, `atlas_step_runner.py`, DAGs | `dag_import`, airflow tests | step contract |
| Audit-table interface | `sql/migrations/*`, `src/atlas/ops` | `sql_migrations`, `schema_compatibility` | `atlas_ops.*` schemas |
| Structured-log event contract | `src/atlas/observability/logging` | `observability_config`, tests | correlation ids, redaction |
| Monitoring configuration | `observability/{metrics,alerts,dashboards}` | `observability_config` | metric/alert schema |
| Deployment bundle contract | `scripts/build_deployment_bundle.sh` | deploy validation | immutable bundle layout |
| Migration contract | `sql/migrations/` + `checksums.lock` | `gate_schema_compatibility` | additive, immutable (INV-D8) |
| Governance metadata contract | dbt `meta.governance` + `governance/*.yml` | `gate_governance` | required fields (INV-G1..3) |
| Schema-compatibility inputs | `governance/schemas/manifests/baseline.json` | `gate_schema_compatibility` | baseline vs candidate |
| Lineage artifact inputs | dbt `ref()`/`source()` + `consumers.yml` | `gate_lineage_impact` | `governance/generated/lineage.json` |
| Cost-control configuration | `config/cost_controls.yaml` | `gate_performance_cost`, `cost_guard` | per-env ceilings |
| Approval variables | `ATLAS_APPROVE_*` env | scripts + gates | see [agent-onboarding.md](../handoff/agent-onboarding.md) |
| Reference/evidence contract | `reference-manifest.yml`, `evidence-index.json` | `atlas.reference.validate`, `gate_reference_handoff` | Sprint 8 |

## Contract-change rule

Changing any interface above requires: (1) updating the definition **and** its
enforcement together; (2) classifying the change via
[schema-evolution-policy-sprint7.md](../schema-evolution-policy-sprint7.md) when
it affects a schema; (3) a consumer-impact run
(`python -m atlas.governance.impact --asset <id>`); (4) updating tests and the
[evidence index](evidence-index.md). Never change a definition while leaving its
enforcement or consumers stale.
