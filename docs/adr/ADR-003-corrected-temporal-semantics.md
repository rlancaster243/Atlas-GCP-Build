# ADR-003: Corrected Sprint 2 Temporal Quality Semantics

## Status

Accepted

## Context

Sprint 1 validation labeled 300 rows as "late_arriving_events" using
`event_date < DATE(event_timestamp)`. Those rows are backdated declared dates, not true
event-time late arrivals relative to ingestion time.

## Decision

Sprint 2 dbt models use corrected flags:

| Flag | Definition | Expected on validated run | Blocking |
| --- | --- | ---: | --- |
| `is_future_dated` | `DATE(event_timestamp) > DATE(ingested_at)` | 150 | Yes |
| `is_event_time_late_arriving` | `DATE(event_timestamp) < DATE(ingested_at)` | 0 | No |
| `is_backdated_event_date` | `event_date < DATE(ingested_at)` | 300 | No |
| `has_event_date_timestamp_mismatch` | `event_date != DATE(event_timestamp)` | 300 | No |

The 300 backdated and 300 mismatch populations are the same physical records and must not
be double-counted during reconciliation.

## Consequences

- Sprint 1 generator and raw data remain unchanged for auditability.
- Sprint 2 documentation and singular tests use the corrected definitions.
- Warning flags may coexist on accepted canonical rows.

## Sprint 3 refinement — reproducible temporal semantics for backfills

### Context

The Sprint 2 flags above reference wall-clock `DATE(ingested_at)`. That makes
event classification (accept/reject) a function of *when the pipeline physically
ran*: a historical batch (e.g. `processing_date = 2026-07-01`) ingested on
2026-07-18 flips `future_dated` 150→0, `event_time_late` 0→~50000, and
`backdated` 300→~50000. This broke the Sprint 3 batch-identity/backfill guarantee
(ADR-006): reprocessing the same raw batch produced different `fct_events`/marts
and failed `assert_source_anomaly_profile`.

### Decision

Evaluate the three ingestion-relative flags against the batch's **logical
processing date** instead of wall-clock ingest time:

| Flag | Sprint 3 definition |
| --- | --- |
| `is_future_dated` | `DATE(event_timestamp) > COALESCE(processing_date, DATE(ingested_at))` |
| `is_event_time_late_arriving` | `DATE(event_timestamp) < COALESCE(processing_date, DATE(ingested_at))` |
| `is_backdated_event_date` | `event_date < COALESCE(processing_date, DATE(ingested_at))` |
| `has_event_date_timestamp_mismatch` | `event_date != DATE(event_timestamp)` (unchanged, already reproducible) |

`processing_date` is a new nullable column on `atlas_raw.events`, persisted by the
loader per batch. Legacy Sprint 1 rows have `processing_date = NULL` and fall back
to `DATE(ingested_at)`, preserving prior behavior. `assert_source_anomaly_profile`
asserts the temporal counts only when every scoped row carries `processing_date`,
degrading gracefully for legacy scopes.

### Consequences

- Historical backfills classify identically to the original run (verified live:
  batch `atlas-20260701` recovered `FAILED`→`SUCCESS`; fresh historical batch
  `atlas-20260716` loaded and passed with native `processing_date`).
- For same-day batches `processing_date == DATE(ingested_at)`, so the expected
  150 / 0 / 300 / 300 profile is unchanged.
