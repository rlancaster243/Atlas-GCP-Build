# Atlas Sprint 6 Validation Report — Resilience, Failure Engineering, Recovery, Game Days

All claims below are backed by live execution on 2026-07-19 in project
`example-gcp-project`, by GitHub CI runs, or by unit/acceptance tests in this
repository. Anything not proven live is stated as such under coverage and
limitations.

## 1. Git and PR evidence

| Item | Value |
| --- | --- |
| Sprint 6 base (origin/main) | `078bc319c6683717e6583b4500af60b4dd3e168a` |
| Sprint 6 branch / PR | `cursor/atlas-sprint-6-resilience-64a2` / PR #21 |
| Candidate git_sha at live acceptance | `b735823bc5193782bad73a73f3222a2eeafafbae` |
| CI on candidate | run `29691106793` — atlas-ci **success** (all gates) |
| Earlier green iteration | run `29689314252` (success) |

## 2. Deployed release during acceptance

| Release SHA | Deployment id | Result |
| --- | --- | --- |
| `b735823` | `atlas-dev-20260719T145242Z-b735823b` | SUCCESS — 12/12 smoke checks; migrations 007/008 applied |

Composer environment: `atlas-dev`, `composer-3-airflow-3.1.7-build.13`,
us-central1, SMALL. Both DAGs parse with zero import errors. Env vars include
`ATLAS_LOG_TO_CLOUD_LOGGING=true`, `ATLAS_ENVIRONMENT=atlas-dev` (Sprint 5
log-export mitigation, now set at create time). Lifecycle is ephemeral (ADR-010):
created 2026-07-19T14:31Z, deleted at end of acceptance (teardown gated on
`ATLAS_APPROVE_TEARDOWN`, recorded below).

## 3. Schema changes (live)

| Migration | State |
| --- | --- |
| `007_create_recovery_actions_table` | APPLIED — `atlas_ops.recovery_actions` present (20 columns) |
| `008_add_task_event_timing_columns` | APPLIED — `atlas_ops.task_events` has `timing_source`, `timing_confidence` |

## 4. The nine resilience obligations — evidence

| # | Obligation | Evidence |
| --- | --- | --- |
| 1 | Detect failures | Ingestion retry (S6-ING-006), dbt test failure (S6-DBT-002), overlapping runs (S6-AIR-004), cost-guard blocks (S6-COST-002/003) all surfaced with `task_events`/`pipeline_runs`/telemetry — see `game-day-results-sprint6.md` |
| 2 | Contain failures | Failed runs published no success marker; DAG paused to stop scheduler contention (INC-S6-002); cost guards block before spend |
| 3 | Diagnose failures | Root causes established from `task_events`, `INFORMATION_SCHEMA.JOBS`, dbt output, and row-count queries (INC-S6-001/002) |
| 4 | Recover with control | `QUARANTINE_BATCH` targeted repair (no full refresh) — INC-S6-001 |
| 5 | Verify recovery | `validate_warehouse("atlas-20260717")` = 10/10 PASS post-recovery; `SUCCESS` gated on `VERIFIED` in `recovery_actions` |
| 6 | Prevent recurrence | Follow-ups documented per incident; DAG pause during deploy window |
| 7 | Preserve data correctness | Global dedup keeps one row per `event_id`; baseline reconciles 10/10 throughout |
| 8 | Durable operational history | `pipeline_runs`, `task_events` (now with timing provenance), `recovery_actions`, `quality_results` |
| 9 | Reproducible evidence | This report + `game-day-results-sprint6.md` + two incident reports, all with concrete ids |

## 5. Failed-task timing provenance (Phase 1 fix)

Before Sprint 6, terminal task events recorded by the Airflow failure callback
overwrote `started_at`/`completed_at`/`duration_ms` with NULL. After the fix,
FAILED/RETRY events carry non-null timing plus provenance
(`timing_source` ∈ {`step_runner_clock`, `airflow_task_instance`};
`timing_confidence` ∈ {`exact`, `partial`, `none`}). Verified live on run
`atlas-airflow-20260719-baseline-s6-20260719` (see game-day results).
Regression tests: `tests/airflow/test_callback_timing.py`.

## 6. Static / CI coverage

`scripts/validate_ci.sh` (static mode) is green, including the new
`gate_failure_injection` gate (catalog schema valid; fault injection disabled by
default; not hardcoded in production paths). Unit/airflow tests added:
`test_failure_injection.py`, `test_recovery_actions.py`, `test_cost_guards.py`,
`test_callback_timing.py`, plus `test_run_context.py` backfill-guard cases.

## 7. Live acceptance coverage vs. static coverage

Live-injected this window: S6-ING-006, S6-DBT-002/004, S6-AIR-004, S6-COST-002,
S6-COST-003, plus a full verified `QUARANTINE_BATCH` recovery and the fault
-injection safety gate. Per the game-day plan, the remaining catalog scenarios
(deploy/rollback ledger checks, schema-version normalization, rollback
compatibility, dry-run ceiling, guarded query config, and the additional
ingestion/warehouse/IAM/observability variants) are proven by CI gates and unit
tests rather than live injection, to keep the ephemeral, cost-bounded Composer
window short (ADR-010) and to avoid destructive cloud operations. This split is
explicit and honest: it is a deliberate scope decision, not a coverage claim
that live injection did not occur.

## 8. Exit state and teardown

- Healthy baseline `atlas-20260717` reconciles 10/10 (post-recovery).
- INC-S6-001 recovered + VERIFIED; INC-S6-002 contained.
- `recovery_actions` holds one VERIFIED row (`rec-s6-quarantine-atlas20260719`).
- Alert policies restored to repo-defined state (10/10 ENABLED) before teardown.
- Composer deleted under `ATLAS_APPROVE_TEARDOWN`: both DAGs paused →
  environment-dependent alerts disabled (`Atlas: data stale`,
  `Atlas: Composer environment unhealthy`) → environment deleted
  (2026-07-19T16:14Z, ≈ 1.7 h lifecycle from 14:31Z) → orphaned Composer bucket
  removed (381 objects) → `composer environments list` = 0 items. Permanent
  resources (audit tables incl. `recovery_actions`, log bucket/sink/view, metric
  descriptors, the 8 non-environment alert policies, notification channel,
  dashboard) remain valid; the recovery audit row survives teardown.

## 9. Unresolved limitations

- The batch-scoped anomaly-profile test is sensitive to same-date reprocessing
  (INC-S6-001 root cause). Recommended fixes are listed in that incident report;
  they are Sprint 7 candidates, not regressions introduced by Sprint 6.
- Live game-day coverage is a representative subset (section 7); full live
  injection of all 56 catalog scenarios was intentionally not performed.
