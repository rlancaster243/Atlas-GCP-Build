# ADR-006: Stable Batch Identity and Immutable Ingestion

## Status

Accepted — 2026-07-14

## Context

Sprint 1 keyed raw loads on `pipeline_run_id`, preventing safe reruns of the same
data batch under a new execution identity.

## Decision

Introduce `batch_id` as the stable data identity and keep `pipeline_run_id` as the
execution identity. GCS paths use `batch_id=` prefixes with checksum metadata.
Raw loads evaluate batch row counts (0/load, exact/skip, partial-fail, excess-fail).

## Consequences

- Sprint 1 rows retain `batch_id IS NULL`.
- dbt models propagate `batch_id` for Airflow-scoped reconciliation tests.

## Sprint 7 amendment: replay and duplicate semantics

INC-S6-001 exposed a defect: `int_event_classification` computed a single
**global** duplicate rank and the batch-scoped anomaly profile counted it, so a
same-date reprocessing batch (whose deterministic generator produces identical
`event_id`s) inflated the within-batch duplicate count to the whole batch and
failed `assert_source_anomaly_profile`. Global fact uniqueness was fine; the
classification/measurement conflated two distinct concepts.

Sprint 7 makes the semantics explicit. Every classified row now carries:

- `within_batch_duplicate_rank` — `row_number()` partitioned by
  `(coalesce(batch_id, pipeline_run_id), event_id)`, latest write wins.
- `is_within_batch_duplicate` — `within_batch_duplicate_rank > 1`. This is the
  **batch-scoped data-quality anomaly** (the 50 intentional extras).
- `duplicate_rank` — global canonical rank per `event_id`, ordered
  `within_batch_duplicate_rank asc, ingested_at asc, …`. **First-seen batch
  wins**, so a replay never disturbs an already-published canonical prior batch;
  within a batch, latest still wins.
- `is_duplicate_extra` — `duplicate_rank > 1` (feeds `rejection_reason`;
  preserves exactly one canonical row per `event_id`).
- `duplicate_scope` — `within_batch` | `cross_batch_replay` | `none`.

The anomaly profile now counts `is_within_batch_duplicate` (batch-scoped), so a
stray same-date batch no longer corrupts a healthy batch's profile, and
cross-batch replays are separately measurable via `duplicate_scope`.

### Invariants (unchanged or newly guaranteed)

| Invariant | How preserved |
| --- | --- |
| Exact batch rerun idempotent | raw load is create-only per batch; classification deterministic |
| Same date, different batch | classified as `cross_batch_replay`, rejected; first batch stays canonical |
| 50 within-batch extras detectable | `is_within_batch_duplicate` counts exactly them |
| Cross-batch replay measurable | `duplicate_scope = 'cross_batch_replay'` |
| Global fact uniqueness | `fct_events` `unique_key = event_id`; one canonical accepted row |
| accepted + rejected = raw | classification preserves physical-row grain |
| Prior healthy batches stable | first-seen-wins canonical ordering |
| Historical backfills deterministic | ordering uses only stable row attributes |

Tested by dbt unit tests (`test_cross_batch_replay_preserves_first_seen`,
`test_duplicate_ranking_keeps_latest_canonical`, precedence/warning tests) and
verified live in the Sprint 7 acceptance window. `fct_events` grain is unchanged
(one row per `event_id`); this amendment does not change that grain.
