# Atlas Sprint 7 Architecture — Governance Layer

Sprint 7 adds an **enforceable governance layer** over the Sprint 1–6 platform.
No data-plane redesign: the ingestion → dbt warehouse → orchestration →
CI/CD → observability → resilience stack is unchanged. Sprint 7 makes changes to
data, schemas, permissions, retention, warehouse structure, and cost *governed*.

## Components added

```
governance/                         # source of truth (declarative)
  policy.yml                        # rules + controlled vocabularies
  classifications.yml               # PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED
  retention.yml                     # retention classes + disposal
  consumers.yml                     # internal consumer registry
  non_dbt_assets.yml                # raw/ops/bucket/dag/dashboard/log assets
  changes/TEMPLATE.yml              # schema-change records (ADR-017)
  schemas/                          # JSON schema + versioned manifests
    manifests/baseline.json         # committed schema baseline
  generated/                        # DERIVED (catalog.json/md, lineage.json)

dbt models: meta.governance blocks  # source of truth for models

src/atlas/governance/
  registry.py     # load + validate governance; deprecation lifecycle
  catalog.py      # generate consolidated catalog (+ drift check)
  schema_check.py # compatibility classification + manifest generation
  lineage.py      # dbt ref/source -> lineage graph
  impact.py       # consumer-impact analysis
  security_policy.py # managed-IAM + data-exposure scanners
  retention.py    # retention validation + disposal planning
src/atlas/observability/
  cost_guard.py   # config-driven cost ceilings + estimate CLI (Sprint 7)
  cost_guards.py  # Sprint 6 runtime guards (extended)

config/cost_controls.yaml           # per-env cost ceilings
sql/migrations/checksums.lock        # applied-migration immutability
observability/performance/           # perf query set + suite results
scripts/run_performance_suite.sh     # dry-run baseline + gated execution
```

## Enforcement (CI gates, all offline/credentialless)

`scripts/validate_ci.sh --group python` runs, in addition to the prior gates:

- `gate_governance` — complete metadata, one source of truth, no catalog drift,
  retention invariants, deprecation lifecycle.
- `gate_schema_compatibility` — migration checksum immutability + schema
  baseline drift.
- `gate_lineage_impact` — lineage drift + source→mart reachability.
- `gate_security_policy` — no prohibited IAM roles/keys in managed defs, no
  secret-like values in governed artifacts.
- `gate_performance_cost` — cost-control config coherence.

## Data flow with governance overlaid

```
generate_events → raw → staging → classification → accepted/rejected
   → fact → dims → marts → operational tables
        │            │          │            │
   contracts    dup/replay   schema       lineage +
   (ADR-016)    semantics    compat        impact
                (ADR-006amd) (ADR-017)     (Phase 5)

   classification + retention (ADR-019) apply to every asset
   cost + performance controls (ADR-020) apply to every query
   IAM boundaries (ADR-018) apply to every identity
```

## Key invariant preserved

`fct_events` grain remains **one row per event_id** (global uniqueness). The
Sprint 3 defect fix (ADR-006 amendment) changed duplicate *classification and
measurement*, not the fact grain.

## What Sprint 7 did NOT change

Data-plane models (except the classification-semantics fix), orchestration DAGs,
deploy/rollback flow, observability metrics/alerts/dashboard, and the
