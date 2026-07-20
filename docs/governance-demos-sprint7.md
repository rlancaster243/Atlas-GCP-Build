# Atlas Governance Enforcement Demonstrations (Sprint 7, Phase 14)

Each required demonstration and where it is proven. All destructive/breaking
cases use fixtures or loader injection — no defect is ever merged to main.

| # | Demonstration | Evidence | Type |
| --- | --- | --- | --- |
| 1 | Missing owner fails governance CI | `test_governance_demos.py::test_missing_owner_fails` | fixture |
| 2 | Missing grain fails governance CI | `test_governance_demos.py::test_missing_grain_fails` | fixture |
| 3 | Additive nullable schema change passes | `test_schema_check.py::test_added_nullable_field_is_compatible` | fixture |
| 4 | Breaking type change fails | `test_schema_check.py::test_type_change_is_breaking` | fixture |
| 5 | Applied migration checksum modification fails | `test_governance_demos.py::test_migration_checksum_tamper_is_detected` + `gate_schema_compatibility` | fixture |
| 6 | Deprecated field without replacement fails | `test_deprecation.py::test_deprecated_without_replacement_fails` | fixture |
| 7 | Removed asset with active consumer fails | `test_deprecation.py::test_removed_asset_with_active_consumer_fails` | fixture |
| 8 | Impact report identifies downstream models | `test_lineage_impact.py::test_impact_identifies_downstream_models` | fixture |
| 9 | Secret-like fixture fails scanning without printing value | `test_security_policy.py` (scan_text returns reasons, not values) | fixture |
| 10 | Invalid retention configuration fails | `test_retention.py::test_conflicting_permanent_expiration_fails` | fixture |
| 11 | Unbounded query exceeds dry-run ceiling and is blocked | live dry-run demo (Phase 15/16) — `cost_guard estimate` | live (dry-run, $0) |
| 12 | Required partition filter absence detected | `test_cost_guard.py::test_required_partition_filter_missing_raises` | fixture |
| 13 | Unauthorized identity denied a protected operation | IAM negative test — **blocked on `ATLAS_APPROVE_IAM`** (plan in iam-review) | live (gated) |
| 14 | Authorized identity completes the operation | IAM positive test — **blocked on `ATLAS_APPROVE_IAM`** | live (gated) |
| 15 | Same-date reprocessing → correct duplicate/replay classification | dbt `test_cross_batch_replay_preserves_first_seen` (PASS live) | fixture (live dbt) |
| 16 | Exact rerun remains idempotent | dbt `test_duplicate_ranking_keeps_latest_canonical` (PASS live) + fct merge unique_key | fixture (live dbt) |

## Notes

- Demonstrations 1–10, 12, 15, 16 are proven offline / via live dbt unit tests
  and pass in CI.
- Demonstration 11 is proven in the live acceptance window with a dry-run
  estimate (bills $0) — `python -m atlas.observability.cost_guard estimate` on a
  deliberately unbounded query returns `BLOCKED` before any spend.
- Demonstrations 13–14 (live IAM positive/negative) require
  `ATLAS_APPROVE_IAM=true`; the exact reduction and test plan are in
  `iam-review-sprint7.md`. Recorded as a blocked gate; not weakened, not faked.
