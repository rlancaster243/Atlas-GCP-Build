# Atlas Governance (Sprint 7)

This directory is the **governance source of truth** for Project Atlas. It makes
ownership, classification, retention, contracts, and lifecycle *enforceable* by
CI rather than living in prose (ADR-016).

## Source-of-truth split

| Asset kind | Authoritative source |
| --- | --- |
| dbt models (staging/intermediate/core/marts) | dbt `meta.governance` blocks in `dbt/atlas_dbt/models/**/*.yml` |
| Non-dbt assets (raw/ops tables, buckets, DAGs, dashboards, logs) | `governance/non_dbt_assets.yml` |
| Consolidated catalog | **generated** into `governance/generated/` — never hand-edited |

The same metadata is never maintained in two places. dbt models are **not**
listed in `non_dbt_assets.yml`; governance CI fails if an id appears in both.

## Files

- `policy.yml` — the rules: required fields, controlled vocabularies, owner
  rules, deprecation window, source-of-truth map.
- `classifications.yml` — PUBLIC / INTERNAL / CONFIDENTIAL / RESTRICTED meanings.
- `retention.yml` — retention classes and disposal policy.
- `consumers.yml` — internal consumer registry (used by impact + deprecation).
- `non_dbt_assets.yml` — non-dbt asset registry.
- `schemas/` — JSON Schemas for the registry files.
- `changes/` — schema-change proposal records (see the schema-evolution policy).
- `schemas/manifests/` — versioned schema baselines for compatibility checks.
- `generated/` — generated catalog (`catalog.json`, `catalog.md`).

## Commands

```bash
# Validate governance metadata against policy.yml (offline, no credentials):
python -m atlas.governance.catalog check

# Regenerate the consolidated catalog after changing sources:
python -m atlas.governance.catalog generate
```

Governance validation also runs in CI via `gate_governance` in
`scripts/validate_ci.sh`.

## Adding or changing an asset

1. dbt model: edit its `meta.governance` block in the model's `.yml`.
2. Non-dbt asset: edit `governance/non_dbt_assets.yml`.
3. Run `python -m atlas.governance.catalog generate` and commit the regenerated
   catalog.
4. For schema/contract changes, add a change record under `governance/changes/`
   (see `docs/schema-evolution-policy-sprint7.md`).
