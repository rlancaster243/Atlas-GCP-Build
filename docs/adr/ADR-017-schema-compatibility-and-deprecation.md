# ADR-017: Schema Compatibility and Deprecation

- Status: Accepted (Sprint 7)
- Date: 2026-07-19
- Deciders: lead data architect, data engineering, CI policy engineer
- Supersedes/extends: ADR-015 (schema compatibility and recovery)

## Context

Atlas had rollback compatibility (ADR-015) and a migration ledger, but no
automated way to classify whether a proposed schema/contract change is safe, and
no enforcement that breaking changes carry an approved migration. Sprint 7 makes
schema evolution a governed, testable process.

## Decision

### Compatibility classes

Every schema/contract change is classified by `atlas.governance.schema_check`:

- **COMPATIBLE** — additive nullable column, widened accepted-value set,
  description/ownership improvement, additive non-breaking metadata,
  required→nullable loosening, a brand-new asset.
- **CONDITIONALLY_COMPATIBLE** — requires consumer migration (e.g. a new
  required field), approved temporary alias, approved dual-write period,
  approved type widening with evidence, or deprecation with an active
  replacement.
- **BREAKING** — removed/renamed field without a compatibility path,
  incompatible type change, nullable→required without migration, changed model
  grain, changed partition field, changed event identity, or a narrowed enum
  that rejects existing valid values.
- **PROHIBITED** — destructive canonical change without approval, unversioned
  contract replacement (schema changed but `contract_version` unchanged or
  downgraded), changing an applied migration checksum, silent field reuse with
  different semantics, or bypassing consumer-impact analysis.

### Versioned baselines

`governance/schemas/manifests/baseline.json` is a committed, generated snapshot
of every dbt model's contract-relevant schema (fields, types, nullability,
accepted values, grain, partition field, event identity, contract version). CI
regenerates it and fails on drift, so the baseline can never silently rot.

### Checker interface

```
python -m atlas.governance.schema_check --baseline <manifest> \
    --candidate <manifest> --output <report> [--fail-on BREAKING]
python -m atlas.governance.schema_check --generate <manifest>
```

### Change records

Every non-COMPATIBLE change must ship a change record under
`governance/changes/` declaring: `change_id`, `asset_id`,
`old_contract_version`, `new_contract_version`, `compatibility_class`, `reason`,
`owner`, `consumer_impact`, `migration_plan`, `backfill_plan`, `validation_plan`,
`rollback_limitations`, `deprecation_window`, `approval_reference`. CI
(`gate_schema_compatibility` + `gate_governance`) rejects a BREAKING change that
lacks a complete, approved change record.

### Applied-migration immutability

`sql/migrations/checksums.lock` pins the SHA-256 of every shipped migration.
`gate_schema_compatibility` fails if any migration file's checksum diverges from
the lock (PROHIBITED). New migrations must append a lock entry; existing ones
can never be edited.

## Alternatives considered

- **Rely only on `on_schema_change=fail` in dbt.** Insufficient: it catches
  fact-table column drift at build time but not grain/partition/identity/enum
  changes, contract versioning, or migration edits, and gives no PR-time
  classification.
- **Register schemas in an external registry.** Out of scope; committed
  manifests suffice at this scale.

## Consequences

- Additive changes pass CI automatically; breaking changes are blocked unless an
  approved change record exists.
- Applied migrations are provably immutable.
- Never demonstrate a breaking change against canonical Atlas data — fixtures
  only (`ATLAS_APPROVE_BREAKING_SCHEMA_DEMO`).

## Honest limitations

- The generated manifest infers types only where dbt declares `data_type`
  (currently the enforced `stg_events` contract); other columns record type
  `unknown`, so type-change detection is strongest on contracted columns.
  Nullability and accepted-values are inferred from dbt tests.
