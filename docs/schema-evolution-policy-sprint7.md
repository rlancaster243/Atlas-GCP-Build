# Atlas Schema Evolution Policy (Sprint 7)

How Atlas schemas and contracts change safely. Enforced by
`atlas.governance.schema_check` + `gate_schema_compatibility`. See ADR-017.

## The workflow

```
1. Edit a model/table schema or governance meta.
2. Regenerate the baseline manifest and run the checker:
     python -m atlas.governance.schema_check --generate \
       governance/schemas/manifests/baseline.json
     python -m atlas.governance.schema_check \
       --baseline <old> --candidate governance/schemas/manifests/baseline.json \
       --output report.json
3. Read the overall_class:
     COMPATIBLE               -> bump minor contract_version, ship.
     CONDITIONALLY_COMPATIBLE -> add a change record + migration/dual-write plan.
     BREAKING                 -> add an APPROVED change record; bump major.
     PROHIBITED               -> stop; the change is not allowed as written.
4. Commit the regenerated baseline (CI fails on drift).
```

## Compatibility classes (summary)

| Class | Examples | CI |
| --- | --- | --- |
| COMPATIBLE | add nullable field, widen enum, loosen nullability, new asset, metadata | passes |
| CONDITIONALLY_COMPATIBLE | add required field, type widening w/ evidence, dual-write, deprecation w/ replacement | passes **with** complete change record |
| BREAKING | remove/rename field, type change, tighten nullability, change grain/partition/identity, narrow enum | fails without an **approved** change record |
| PROHIBITED | unversioned change, contract downgrade, edit an applied migration, silent field reuse | always fails |

## Change records

Location: `governance/changes/<change_id>.yml` (template:
`governance/changes/TEMPLATE.yml`). Required fields: `change_id`, `asset_id`,
`old_contract_version`, `new_contract_version`, `compatibility_class`, `reason`,
`owner`, `consumer_impact`, `migration_plan`, `backfill_plan`, `validation_plan`,
`rollback_limitations`, `deprecation_window`, `approval_reference`.

A BREAKING change must set `approval_reference` (e.g. an approval variable or PR
approval id) and a `migration_plan`; otherwise CI blocks the merge.

## Contract versioning

`contract_version` is `major.minor`. A schema change with an unchanged or
decreased version is PROHIBITED (unversioned replacement). Minor bump for
COMPATIBLE changes; major bump for CONDITIONALLY_COMPATIBLE / BREAKING.

## Applied-migration immutability

`sql/migrations/checksums.lock` pins each migration's SHA-256. Editing a shipped
migration changes its checksum and fails `gate_schema_compatibility`. Add new
migrations by appending both the manifest line and a lock entry (regenerate with
the helper), never by editing an existing file.

## Never against canonical data

Breaking-change demonstrations use isolated fixtures only, gated by
`ATLAS_APPROVE_BREAKING_SCHEMA_DEMO=true`. Canonical Atlas tables are never
mutated to demonstrate a breaking change.
