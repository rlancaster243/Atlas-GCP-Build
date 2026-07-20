# Atlas Sprint 6 — Game-Day Results & Live Evidence

Ephemeral Composer window: `atlas-dev`
(`composer-3-airflow-3.1.7-build.13`), created 2026-07-19T14:31Z, bucket
`gs://us-central1-atlas-dev-48d75b29-bucket`. Candidate git_sha
`b735823bc5193782bad73a73f3222a2eeafafbae`, deployment_id
`atlas-dev-20260719T145242Z-b735823b` (smoke 12/12, migrations 007/008 applied).

This document records what was proven **live** in the game-day window, and what
is proven by CI gates and unit tests (per the game-day plan, several scenarios
are deliberately covered by static gates rather than live injection to keep the
ephemeral, cost-bounded window short — ADR-010, ADR-013).

## Preconditions verified

| Precondition | Evidence |
| --- | --- |
| Candidate deployed + smoke-validated | deployment_id `atlas-dev-20260719T145242Z-b735823b`, 12/12 smoke checks PASS |
| Migrations 007 (recovery_actions) + 008 (task_event timing) applied | `bq show atlas_ops.recovery_actions` (20 cols); `task_events` has `timing_source`,`timing_confidence` |
| Baseline healthy batch reconciled 10/10 | batch `atlas-20260717`, run `atlas-airflow-20260717-baseline-s6-clean-20260717` SUCCESS; `quality_results` = 10/10 PASS |
| Alert policies restored | all 10 Atlas policies ENABLED (re-enabled `Atlas: data stale`, `Atlas: Composer environment unhealthy`) |
| Notification channel verified recipient | `the primary operator.lancaster243@gmail.com`, enabled |
| Fault injection disabled by default | `cli run` REFUSED without `ATLAS_APPROVE_FAILURE_INJECTION=true`; catalog `validate` = VALID |

## Live evidence captured

### GD1 — Ingestion & idempotency

**S6-ING-006 transient failure → retry-then-success (LIVE, organic).**
Run `atlas-airflow-20260719-baseline-s6-20260719` with `upload_once=true` injected
a one-shot `--fail-once` on `upload_events`:

```
upload_events FAILED  attempt 1  (command exited 1)   src=step_runner_clock conf=exact dur=17004ms
upload_events RETRY   attempt 1                        src=airflow_task_instance conf=exact dur=21110ms
upload_events SUCCESS attempt 2
```

Proof obligation met: RETRY task event then SUCCESS; downstream proceeded; no
duplicate raw load (raw for the batch stayed single-copy, 1 pipeline_run_id).

### GD2 — Warehouse & schema

**S6-DBT-002 dbt test failure blocks publication (LIVE, organic).**
The stray canonical batch `atlas-20260719` failed `dbt build` on the singular
test `assert_source_anomaly_profile` ("Got 1 result, configured to fail if != 0").
All 33 downstream models/tests SKIPPED — publication blocked, no marts promotion.
No BigQuery job errored (INFORMATION_SCHEMA JOBS clean), confirming a *test*
failure, not an engine error.

Root cause (data-correctness finding): `generate_events` seeds deterministically
from `processing_date`, so every batch run for a given date emits identical
`event_id`s. `int_event_classification` dedups `event_id` **globally across all
batches**; when a date is processed by multiple batches (smoke, drills, a stray
scheduled catch-up, and the manual baseline all ran for 2026-07-19), the
batch-scoped anomaly test sees `is_duplicate_extra=50000` instead of the expected
50. Documented as **INC-S6-001** with a verified recovery (below).

### GD3 — IAM & orchestration

**S6-AIR-004 overlapping runs (LIVE, organic).** When the deploy promoted and
unpaused the DAG for the smoke run, Airflow also materialised the latest
scheduled interval (`scheduled__2026-07-19T06:00`). The two runs contended on the
shared dbt target tables; the scheduled run's `dbt_build` FAILED at 15:00:16
while the smoke run succeeded. This is a real (unplanned) manifestation of the
overlapping-run hazard S6-AIR-004 catalogs; mitigation applied for the rest of
the window was pausing the DAG so only explicit manual triggers ran.

### GD5 — Cost guards (live legs)

**S6-COST-002 backfill window guard (LIVE).** A baseline attempt with
`processing_date=2026-07-30` (12-day window vs today) FAILED at
`resolve_run_context` — `validate_backfill_window` raised `CostGuardViolation`
before any batch identity was minted or any bytes were scanned. Structured
telemetry `cost_guard_blocked` (observed_value=12, threshold=7) emitted.

**S6-COST-003 full-refresh guard (LIVE).** `require_full_refresh_approval()`
raised `CostGuardViolation` without `ATLAS_APPROVE_FULL_REFRESH=true` and passed
with it; `validate_backfill_window` blocked a 12-day window and allowed it under
`ATLAS_APPROVE_UNBOUNDED_BACKFILL=true`. Both emit `cost_guard_blocked` events.

### Recovery machinery (live, end-to-end)

**INC-S6-001 QUARANTINE_BATCH recovery (LIVE, VERIFIED).** Full recovery lifecycle
recorded in `atlas_ops.recovery_actions`:

```
recovery_id  rec-s6-quarantine-atlas20260719
action_type  QUARANTINE_BATCH   incident INC-S6-001   scenario S6-DBT-004
RUNNING -> SUCCESS / verification_status=VERIFIED
source_state  raw=50000/int=50000/fct=0 for atlas-20260719, anomaly test failed
target_state  raw=0/int=0/fct=0 for atlas-20260719; baseline atlas-20260717 reconciles 10/10 PASS
```

Targeted deletes only (no full refresh) removed the stray batch from
`atlas_raw.events` and `atlas_intermediate.int_event_classification` (50000 rows
each; fct already 0 under global dedup). Verification: post-quarantine counts all
0 for the batch, and `validate_warehouse("atlas-20260717")` returned 10/10 PASS —
the healthy baseline was untouched. `SUCCESS` was only accepted because
`verification_status=VERIFIED` (ADR-014 contract enforced by `_validate`).

### Failed-task timing provenance (Phase 1 fix, live)

`task_events` FAILED/RETRY rows now carry non-null `started_at`,`completed_at`,
`duration_ms` plus `timing_source`/`timing_confidence` — previously NULL for
callback-recorded terminal events:

```
dbt_build       FAILED  src=airflow_task_instance conf=exact dur=146560ms
write_run_summary FAILED src=airflow_task_instance conf=exact dur=14887ms
upload_events   FAILED  src=step_runner_clock     conf=exact dur=17004ms
```

## Coverage proven by CI gates + unit tests (not live-injected)

Per the game-day plan, these are covered by `scripts/validate_ci.sh` gates and
`tests/unit` / `tests/airflow` rather than live injection, to keep the ephemeral
window short and avoid destructive cloud operations:

- Fault-injection safety contract & catalog schema — `gate_failure_injection`,
  `tests/unit/test_failure_injection.py` (disabled by default; refuses
  scheduled/canonical/production; bounded by duration; approvals required).
- Recovery-action audit invariants (SUCCESS⇒VERIFIED, idempotent upsert,
  controlled vocabulary) — `tests/unit/test_recovery_actions.py`.
- Cost guards (dry-run ceiling, backfill window, full-refresh, guarded query
  config) — `tests/unit/test_cost_guards.py` + live legs above.
- Schema-version discrimination / multi-version normalization — ADR-015,
  `atlas.validation.schema_versions` unit tests.
- Rollback schema compatibility (breaking-migration blocks rollback) —
  `atlas.ops.rollback_compatibility`, wired into `deploy_atlas_release.sh`.
- Deploy/rollback ledger & immutable-bundle checks (S6-DEP-001/002/006,
  S6-RBK-003) — existing deployment CI gates + smoke.

## Exit state

- Healthy baseline `atlas-20260717` reconciles 10/10 (verified post-recovery).
- Zero unresolved test incidents: INC-S6-001 recovered + VERIFIED; INC-S6-002
  (overlapping runs) contained by pausing the DAG.
- `recovery_actions` holds a VERIFIED row for the recovery performed.
- All injection variables unset; fault injection disabled by default.
- Alert policies restored to repo-defined state (10/10 ENABLED) before teardown.
