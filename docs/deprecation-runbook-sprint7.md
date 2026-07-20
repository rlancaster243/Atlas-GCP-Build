# Atlas Deprecation Runbook (Sprint 7)

How to retire a governed asset or field safely. Enforced by
`atlas.governance.registry.deprecation_errors` via `gate_governance`.

## Lifecycle

```
ACTIVE → DEPRECATED → REMOVAL_SCHEDULED → REMOVED
```

An asset's `lifecycle_status` lives in its governance metadata (dbt
`meta.governance` or `non_dbt_assets.yml`). Any non-ACTIVE status requires a
`deprecation` block:

```yaml
deprecation:
  replacement: <asset_id or field that replaces this>
  owner: atlas-data-eng
  announcement_date: "2026-07-19"
  deprecation_start: "2026-07-19"
  earliest_removal_date: "2026-09-01"   # >= start + 30 days
  migration_instructions: "How consumers move to the replacement."
  validation_period: "How long the replacement runs in parallel."
  removal_approval: "<approval reference>"   # required for REMOVAL_SCHEDULED/REMOVED
  rollback_limitations: "What cannot be undone after removal."
  change_record: CHG-YYYYMMDD-slug           # must exist under governance/changes/
```

## Procedure

1. **Announce (ACTIVE → DEPRECATED).** Add the `deprecation` block with a
   replacement, a change record under `governance/changes/`, and a removal date
   at least 30 days out. Regenerate the catalog.
2. **Migrate consumers.** Use `python -m atlas.governance.impact --asset <id>`
   to enumerate affected consumers/owners; migrate each to the replacement.
3. **Schedule removal (DEPRECATED → REMOVAL_SCHEDULED).** Only after consumers
   are migrated. Requires `removal_approval`. CI blocks scheduling while active
   consumers still read the asset.
4. **Remove (REMOVAL_SCHEDULED → REMOVED).** After the earliest removal date and
   with zero active consumers. Removal of canonical schema requires
   `ATLAS_APPROVE_SCHEMA_MUTATION=true`.

## CI rejects

| Condition | Rule |
| --- | --- |
| Deprecated asset without a replacement | `require_replacement` |
| Removal date sooner than the minimum window | `minimum_window_days` (30) |
| Removed/scheduled asset with active consumers | active-consumer check |
| Lifecycle change without a change record | `require_change_record` + existence |
| REMOVAL_SCHEDULED/REMOVED without approval | `removal_approval` required |
| Reused field name with changed semantics | ADR-017 `type_changed` / PROHIBITED |

## Demonstration

Enforcement is proven by fixtures in `tests/unit/test_deprecation.py` (missing
replacement, short window, missing/unknown change record, removed-with-consumer,
missing approval). No critical Atlas field is removed for demonstration — the
harmless path is exercised with fixture records only.
