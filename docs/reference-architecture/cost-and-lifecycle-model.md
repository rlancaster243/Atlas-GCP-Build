# Cost and Lifecycle Model

**Status:** CURRENT · **Audience:** operator, reviewer. Authoritative detail:
[cost-review-sprint7.md](../cost-review-sprint7.md),
[performance-review-sprint7.md](../performance-review-sprint7.md),
[retention-policy-sprint7.md](../retention-policy-sprint7.md), ADR-012/019/020.

## Controls (config-driven)

`config/cost_controls.yaml` defines per-environment limits, enforced by
`src/atlas/observability/cost_guard.py` and `gate_performance_cost`:

- **max_query_bytes / max_performance_suite_bytes** — hard byte ceilings.
- **require_partition_filter_assets** — queries over raw must be bounded (INV-O5).
- **max_backfill_days**, **full_refresh_requires_approval**.
- **temporary_dataset_ttl_hours**, **temporary_object_ttl_days**,
  **composer_max_lifecycle_hours**, **log_retention_days**,
  **release_retention_policy**.

## Estimation-first enforcement (proven, $0)

`python -m atlas.observability.cost_guard estimate` and `check-partition-filter`
run a **dry-run first**, compare against the ceiling, and refuse over-limit
execution before any spend. Proven live at $0 in
`docs/evidence-sprint7/cost-guard-block.txt`: an unbounded `atlas_raw.events`
scan is blocked by both the partition-filter guard and the estimate ceiling.

## Lifecycle & retention

- **Composer** — ephemeral; created for acceptance, torn down under
  `ATLAS_APPROVE_TEARDOWN` (INV-L7).
- **Log retention** — bounded by `log_retention_days`.
- **Temporary resources** — CI datasets/GCS prefixes carry TTLs.
- **Release retention** — validated releases retained per `release_retention_policy`.
- **Operational evidence** — permanent audit tables cannot receive transient
  retention (INV-G7); disposal is a validated dry-run plan.

## Cost claims — proven vs not proven (honest)

- **Proven:** dry-run performance baseline (all 9 queries << 1 GiB); partition
  pruning (2.3 MB bounded vs 12.7 MB unbounded); $0 cost-guard block; negligible
  permanent footprint at synthetic scale.
- **NOT proven (BLOCKED):** the executed/billed performance suite requires
  `ATLAS_APPROVE_PERFORMANCE_TESTS` (+ `ATLAS_MAX_PERFORMANCE_TEST_BYTES`); live
  retention/expiration application requires `ATLAS_APPROVE_RETENTION_MUTATION`.
  See [unresolved-risks.md](unresolved-risks.md) RISK-03/04. We do **not** claim
  production-scale cost/performance from a 50k-row synthetic dataset.
