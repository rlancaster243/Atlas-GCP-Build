# Atlas Cost Review (Sprint 7)

Extends the Sprint 6 cost guards with config-driven controls, an
estimation-first CLI, and a required-partition-filter check. See ADR-020.

## Controls (config/cost_controls.yaml)

| Control | atlas-dev | atlas-ci |
| --- | --- | --- |
| max_query_bytes | 1 GiB | 512 MiB |
| max_performance_suite_bytes | 5 GiB | 1 GiB |
| max_backfill_days | 7 | 3 |
| full_refresh_requires_approval | true | true |
| require_partition_filter_assets | raw.events, fct_events | same |
| temporary_dataset_ttl_hours | 24 | 1 |
| temporary_object_ttl_days | 7 | 1 |
| composer_max_lifecycle_hours | 12 | 6 |
| log_retention_days | 30 | 7 |
| release_retention_policy | keep_validated_releases | same |

Inherited runtime guards (Sprint 6): backfill-window, full-refresh approval,
dry-run ceiling, `maximum_bytes_billed` job config.

## Estimation-first enforcement (demonstrated live, $0)

`docs/evidence-sprint7/cost-guard-block.txt`:

1. **Partition-filter guard** blocks the deliberately unbounded raw scan before
   any execution (`exit=2`).
2. **Estimate CLI** dry-runs first (full scan estimate = 12,659,283 bytes,
   billed $0), then refuses execution when the estimate exceeds the ceiling
   (proven with a tightened ceiling → `decision: BLOCKED`, pre-execution).

An over-limit query is therefore refused **before material spend**, requiring an
explicit `ATLAS_APPROVE_COST_OVERRIDE=true` after a documented review.

## Permanent resource footprint

- 9 BigQuery datasets (small; raw 850k rows, fct 392,845 rows, mart 2,804 rows).
- `atlas-observability` log bucket (30-day retention).
- `atlas-deployments-…` release bundle bucket (validated releases retained).
- 10 alert policies, 1 notification channel, 1 dashboard, metric descriptors.
- **Composer: absent** (ephemeral; not created in Sprint 7 — no changed control
  required it).

## Sprint 7 live cost

- Performance baseline: **dry-runs only → $0**.
- Inventory reads (IAM/table counts/dataset settings): a handful of tiny
  metadata/count queries (KB–MB).
- No Composer, no bulk scans, no full refreshes.
- Estimated Sprint 7 live BigQuery spend: **negligible (< a few MB billed
  total)**; the 5 GiB suite ceiling was never approached.

## Proposed hard byte ceiling

`ATLAS_MAX_PERFORMANCE_TEST_BYTES` (suite) defaults to 5 GiB; per-query 1 GiB.
Both overridable only with documented approval. These remain the recommended
ceilings.

## Honest limitations

- Zero-cost operation is not claimed; the footprint above incurs minimal
  ongoing storage/monitoring cost.
