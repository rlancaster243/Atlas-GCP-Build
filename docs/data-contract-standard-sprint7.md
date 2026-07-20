# Atlas Data Contract Standard (Sprint 7)

A data contract is a **versioned, enforceable agreement** about the shape and
semantics of data crossing a boundary. Atlas contracts are not prose — every
clause maps to an executable control. Where a prose clause would disagree with
an executable schema, the executable schema wins and the prose is fixed.

## Boundaries that require a contract

```
generate_events → raw ingestion → staging → classification
  → accepted / rejected → fact → dimensions → marts → operational tables
```

| Boundary | Producer | Consumer | Contract version | Enforced by |
| --- | --- | --- | --- | --- |
| event generation → raw | `generate_events.py` | `load_events.py` | 1.0 | `validate_events.py`, `atlas.validation.schema_versions` |
| raw → staging | `atlas_raw.events` | `stg_events` | 1.0 | dbt source tests, `stg_events` enforced contract (`data_type`s) |
| staging → classification | `stg_events` | `int_event_classification` | 1.1 | dbt tests + unit tests (rejection precedence, dup rank) |
| classification → accepted/rejected | `int_event_classification` | `int_accepted_events` / `int_rejected_events` | 1.0 | dbt `accepted_values` / `not_accepted_values` tests |
| accepted → fact | `int_accepted_events` | `fct_events` | 1.0 | `unique_key=event_id`, `on_schema_change=fail`, unique/not_null tests |
| fact → dimensions | `fct_events` | `dim_users`, `dim_countries` | 1.0 | not_null/unique + relationship tests |
| fact → marts | `fct_events` | `mart_daily_event_metrics` | 1.0 | `unique_combination_of_columns`, reconciliation tests |
| pipeline → operational tables | pipeline code | audit tables | per table | `observability/schema/expected-schemas.json`, migration ledger |

## Required contract clauses

Each contract declares: contract ID, version, producer, owner, consumers, grain,
fields (required/optional, types, accepted values, uniqueness, nullability),
temporal semantics, duplicate semantics, freshness, compatibility policy,
deprecation policy, validation implementation, and recovery expectations.

Governance metadata carries the durable half of this (owner, grain, consumers,
`contract_version`, classification, retention). The executable half lives in dbt
contracts/tests, source tests, the schema manifest, and Python validators.

## Mapping clauses to executable controls

| Clause | Executable control |
| --- | --- |
| Fields + types | dbt `data_type` (enforced contract on `stg_events`); `expected-schemas.json` for ops tables |
| Required / nullability | dbt `not_null` tests; NULL semantics documented per column |
| Accepted values | dbt `accepted_values` (rejection_reason, platform); `dim_countries` FK |
| Uniqueness | dbt `unique` (event_id, user_id); `unique_combination_of_columns` (mart grain) |
| Grain | governance `grain` field + the uniqueness tests that enforce it |
| Temporal semantics | Sprint 2 corrected flags (`is_future_dated`, late/backdated/mismatch) + `assert_source_anomaly_profile` |
| Duplicate semantics | `int_event_classification` rank + Sprint 7 replay classification (ADR-017) |
| Freshness | `dbt source freshness`; observability freshness check |
| Compatibility policy | `atlas.governance.schema_check` (ADR-017) + `gate_schema_compatibility` |
| Deprecation policy | governance `lifecycle_status` + `governance/changes/` + deprecation CI |
| Migration checksum immutability | `atlas_ops.schema_migrations` ledger + `sql_migrations` checksum gate |
| Recovery expectations | `atlas.ops.recovery_actions` + `docs/recovery-runbook-sprint6.md` |

## Contract versioning

`contract_version` is `major.minor`:

- **minor** bump: backward-compatible change (added nullable field, widened
  accepted set, description/owner improvement) — `COMPATIBLE` in ADR-017.
- **major** bump: a change requiring consumer migration or a breaking change —
  requires a change record and approval (`CONDITIONALLY_COMPATIBLE`/`BREAKING`).

The compatibility class (ADR-017) and the version bump must agree; CI enforces
that a breaking change cannot ship as a minor bump without an approved change
record.

## Non-negotiables

- No prose-only contract that disagrees with the executable schema.
- No unversioned contract replacement (`PROHIBITED`).
- No silent field reuse with changed semantics (`PROHIBITED`).
- Applied migration checksums are immutable (`PROHIBITED` to change).
