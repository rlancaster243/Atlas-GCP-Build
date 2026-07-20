# Atlas Incident Report — INC-S6-001: Same-Date Batch Contamination

Status: closed (recovered, verified). This report documents a genuine
data-correctness incident discovered during the Sprint 6 live game-day window: a
stray scheduled catch-up batch reprocessed a date already processed by several
other batches, breaking the batch-scoped anomaly-profile quality gate. Recovered
by a targeted `QUARANTINE_BATCH` action, audited in `atlas_ops.recovery_actions`.
All timestamps are UTC on 2026-07-19.

## Summary

| Field | Value |
| --- | --- |
| Incident id | INC-S6-001 |
| Title | Canonical `dbt build` blocked — same-date batch contamination |
| Catalog scenario | S6-DBT-002 (test-failure blocks publication) / S6-DBT-004 (duplicate grain) |
| Severity | HIGH (publication blocked; no bad data published) |
| Affected component | `atlas_batch_pipeline` / `dbt_build` → `assert_source_anomaly_profile` |
| Affected batch | `atlas-20260719` (stray scheduled catch-up run) |
| Detection source | `dbt build` singular test failure; `pipeline_runs` FAILED |
| Data impact | None published — quality gate stopped promotion; contamination confined to raw/intermediate and removed on recovery |
| Recovery | `QUARANTINE_BATCH` (targeted deletes, no full refresh), verified |
| Operator | cloud-agent (development ownership model) |

## Timeline (UTC, 2026-07-19)

| Time | Event | Evidence |
| --- | --- | --- |
| 14:31 | Composer `atlas-dev` created; DAG lands paused | `manage_atlas_composer.sh` |
| ~14:53 | Deploy promotes DAG and unpauses for smoke; Airflow materialises latest scheduled interval `scheduled__2026-07-19T06:00` (batch `atlas-20260719`) | deploy log |
| 14:55–15:00 | Scheduled run ingests raw for `atlas-20260719`; `dbt_build` FAILED (contended with concurrent smoke run — see INC-S6-002) | `task_events` |
| 15:18 | Manual baseline `baseline-s6-20260719` (same batch id) — raw already present, idempotent (1 pipeline_run_id, 50000 rows) | `atlas_raw.events` |
| 15:35 | Baseline `dbt_build` FAILED solo on `assert_source_anomaly_profile` — `is_duplicate_extra=50000` (expected 50); 33 downstream SKIP | dbt output, `task_events` |
| 16:04 | Recovery `rec-s6-quarantine-atlas20260719` opened (RUNNING) | `recovery_actions` |
| 16:04 | Targeted deletes: `atlas_raw.events` (-50000), `atlas_intermediate.int_event_classification` (-50000); fct already 0 | `bq` DELETE results |
| 16:05 | Verification: batch counts raw/int/fct = 0/0/0; `validate_warehouse("atlas-20260717")` = 10/10 PASS | `validate_warehouse` |
| 16:05 | Recovery finalized SUCCESS / VERIFIED | `recovery_actions` |

## Technical root cause

`scripts/generate_events.py` derives its seed deterministically from
`processing_date` (`default_seed_for_date`), so **every** batch that processes a
given calendar date emits the *identical* set of `event_id`s. On 2026-07-19 the
date was processed many times: Sprint 5/6 deploy smoke batches, drill batches, a
stray scheduled catch-up run, and a manual baseline.

`models/intermediate/int_event_classification.sql` computes duplicate rank with
`row_number() over (partition by event_id ...)` across the **entire** staged
source (all batches), and flags `duplicate_rank > 1` as `is_duplicate_extra`.
This global dedup is correct for the fact grain (one row per `event_id`), but the
Sprint 2 acceptance test `tests/assert_source_anomaly_profile.sql` asserts an
*exact* per-batch anomaly profile (`duplicate_extra_count = 50`). When a date is
processed by more than one batch, every `event_id` in the newest batch already
exists under an earlier batch, so its rows rank > 1 and
`is_duplicate_extra` inflates to the full batch size (50000). The test returns 1
row → `dbt build` exits non-zero → publication is correctly blocked.

Confirmation it was a *test* failure, not an engine error: no failed BigQuery
jobs in `INFORMATION_SCHEMA.JOBS` for the window; raw/intermediate row counts for
the batch were internally consistent (50000 rows, 49950 distinct event ids = the
50 intentionally-injected duplicates).

## Recovery

Controlled `QUARANTINE_BATCH` (targeted repair, not full refresh — ADR-014):

1. `start_recovery_action(QUARANTINE_BATCH, incident=INC-S6-001, batch=atlas-20260719)` → RUNNING row.
2. `DELETE FROM atlas_raw.events WHERE batch_id='atlas-20260719'` (50000 rows).
3. `DELETE FROM atlas_intermediate.int_event_classification WHERE batch_id='atlas-20260719'` (50000 rows).
4. Verify: raw/int/fct counts for the batch = 0; `validate_warehouse("atlas-20260717")` = 10/10 PASS.
5. `finalize_recovery_action(status=SUCCESS, verification_status=VERIFIED)` — `SUCCESS` accepted only because verification passed (enforced by `_validate`).

The healthy baseline `atlas-20260717` (a date with unique event ids) was never
affected and continued to reconcile 10/10 throughout.

## Blameless analysis & prevention

- The stray scheduled run existed only because the smoke deploy unpauses the DAG,
  and Airflow immediately materialised the latest scheduled interval. For the
  rest of the window the DAG was paused so only explicit manual triggers ran.
- The deeper fragility — the batch-scoped anomaly test being sensitive to
  cross-batch same-date reprocessing — is a real limitation of using a
  date-seeded generator with a global-dedup intermediate. It does **not** affect
  fact correctness (global dedup keeps one row per event id) but it does make the
  Sprint 2 exact-count acceptance test unreliable whenever a date is reprocessed.

### Recommended follow-ups (Sprint 7 candidates)

1. Scope the duplicate-rank window (or the anomaly test) to the batch being
   validated, so cross-batch reprocessing of a date cannot distort a
   batch-scoped acceptance profile.
2. Make smoke/drill batches use event ids namespaced by `batch_id` (or an
   isolated dataset), removing cross-batch `event_id` collisions entirely.
3. Keep production canonical batches one-per-date (already the norm); treat any
   second batch for a date as an incident (this report) rather than a silent
   overwrite.
