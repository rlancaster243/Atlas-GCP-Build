# Atlas Governance Model (Sprint 7)

How Atlas makes ownership, classification, retention, contracts, and lifecycle
**enforceable**. See ADR-016 for the source-of-truth decision.

## The model in one picture

```
dbt meta.governance (models)      governance/non_dbt_assets.yml (everything else)
            \                                   /
             \                                 /
       atlas.governance.registry.validate_governance()   <- policy.yml rules
                              |
                 python -m atlas.governance.catalog generate
                              |
              governance/generated/catalog.json + catalog.md
                              |
                     gate_governance (CI, offline)
```

## What is governed

22 assets today (see `governance/generated/catalog.md`):

- 8 dbt models (staging, intermediate ×3, dimensions ×2, fact, mart) — governed
  by `meta.governance`.
- 14 non-dbt assets (raw table, 7 operational tables, 2 buckets, 2 DAGs,
  1 dashboard, 1 log resource) — governed by the registry.

## Required fields

Every asset declares: `asset_id`, `asset_type`, `purpose`, `technical_owner`,
`business_owner_or_role`, `grain`, `source`, `consumers`, `classification`,
`retention_class`, `freshness_expectation`, `contract_version`,
`lifecycle_status`, `repository_path`, `runbook`, `last_reviewed`.

## Enforced invariants (gate_governance)

- Every asset has all required fields (non-empty).
- `asset_type`, `classification`, `lifecycle_status`, `retention_class` are in
  the controlled vocabulary (`policy.yml`).
- `technical_owner` is a role id (regex), never an email address.
- Every declared consumer is either a registered consumer (`consumers.yml`) or a
  governed asset id.
- **One source of truth:** no asset id appears in both dbt meta and the registry.
- **Retention permanence:** a retention class marked `is_permanent_evidence`
  cannot carry an expiration.
- **No RESTRICTED assets** while `classifications.yml` asserts none exist.
- The committed generated catalog matches a fresh generation (no drift).

## Commands

```bash
python -m atlas.governance.catalog check      # validate + drift check (CI)
python -m atlas.governance.catalog generate   # regenerate catalog after edits
bash scripts/validate_ci.sh --mode static --group python   # includes gate_governance
```

## Lifecycle

`ACTIVE → DEPRECATED → REMOVAL_SCHEDULED → REMOVED`, enforced by the deprecation
workflow (`docs/deprecation-runbook-sprint7.md`, Phase 6).

## Classification & retention

Levels: PUBLIC / INTERNAL / CONFIDENTIAL / RESTRICTED
(`governance/classifications.yml`). Retention classes and disposal policy in
`governance/retention.yml`; see `docs/retention-policy-sprint7.md` (ADR-019).
