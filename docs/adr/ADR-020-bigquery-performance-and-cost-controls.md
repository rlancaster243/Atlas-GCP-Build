# ADR-020: BigQuery Performance and Cost Controls

- Status: Accepted (Sprint 7)
- Date: 2026-07-19
- Deciders: BigQuery performance engineer, cost steward, CI policy engineer
- Extends: ADR-012 (cost attribution), Sprint 6 cost guards

## Context

Sprint 6 added runtime cost guards (backfill window, full-refresh approval,
dry-run ceiling). Sprint 7 makes cost limits **config-driven and enforced before
spend**, and establishes a measured performance methodology.

## Decision

### Config-driven controls

`config/cost_controls.yaml` declares per-environment limits: `max_query_bytes`,
`max_performance_suite_bytes`, `max_backfill_days`,
`full_refresh_requires_approval`, `require_partition_filter_assets`,
`temporary_dataset_ttl_hours`, `temporary_object_ttl_days`,
`composer_max_lifecycle_hours`, `log_retention_days`, `release_retention_policy`.
`gate_performance_cost` validates coherence (per-query ceiling ≤ suite ceiling,
required fields present).

### Estimation-first execution

`python -m atlas.observability.cost_guard estimate` always dry-runs first
(bills $0), reports estimated bytes, compares with the environment ceiling, and
**refuses over-limit execution** unless `ATLAS_APPROVE_COST_OVERRIDE=true`. It
never executes on estimation failure and emits structured evidence.
`ATLAS_MAX_PERFORMANCE_TEST_BYTES` caps the whole performance suite.

### Required partition filters

`check-partition-filter` statically rejects queries over
`require_partition_filter_assets` (raw events, fct_events) that lack a partition
predicate, catching the classic full-scan cost mistake.

### Performance methodology (ADR-020 / performance-review)

Measure before optimizing. Every performance experiment records bytes
processed/billed, slot-ms, elapsed, rows in/out, partition pruning, correctness
checksum, and query plan evidence, under a hard byte ceiling and run labels. A
change ships only if it preserves grain and correctness; "no material
improvement" backed by evidence is an acceptable result.

## Consequences

- An unbounded query is blocked at dry-run before material spend (demonstrated).
- Cost limits live in one config, enforced in CI and at runtime.
- Performance changes are evidence-gated and correctness-preserving.

## Honest limitations

- The dataset is ~50k rows/batch; performance results are engineering
  demonstrations, not production-scale benchmarks.
- The partition-filter check is a static heuristic on partition-column
  predicates, not a full SQL analyzer.
