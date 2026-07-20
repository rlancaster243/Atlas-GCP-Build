# Atlas Sprint 6 Cost and Guardrail Review

Measurements taken live on 2026-07-19 during the Sprint 6 acceptance window in
project `example-gcp-project`. Currency figures use public `us-central1` list
prices and are estimates, not billing-export truth.

## New in Sprint 6: preventive cost guards

Sprint 6 adds `src/atlas/observability/cost_guards.py`, whose entire purpose is
to stop runaway spend *before* it happens. All were exercised live:

| Guard | Behavior | Live evidence |
| --- | --- | --- |
| `validate_backfill_window` | Rejects backfill windows > 7 days unless `ATLAS_APPROVE_UNBOUNDED_BACKFILL=true` | Blocked a 12-day window (`processing_date=2026-07-30`) at `resolve_run_context` — zero bytes scanned; `cost_guard_blocked` (observed 12, threshold 7) emitted |
| `require_full_refresh_approval` | Blocks dbt `--full-refresh` unless `ATLAS_APPROVE_FULL_REFRESH=true` | Blocked without approval, allowed with it; `cost_guard_blocked` emitted |
| `enforce_dry_run_ceiling` / `guarded_query_config` | Caps estimated bytes and sets `maximum_bytes_billed` | Unit-tested (`tests/unit/test_cost_guards.py`) |

These guards make the default posture "incremental, bounded, cheap"; expensive
operations require an explicit, logged approval variable.

## Composer (dominant cost, ephemeral)

| Item | Value |
| --- | --- |
| Environment | `atlas-dev`, `composer-3-airflow-3.1.7-build.13`, ENVIRONMENT_SIZE_SMALL |
| Created | 2026-07-19T14:31Z |
| Deleted | end of acceptance window (teardown gated on `ATLAS_APPROVE_TEARDOWN`) |
| Estimated rate | ≈ $0.60–0.90/hour for a small Composer 3 environment |
| Acceptance window | a few hours ⇒ single-digit dollars |

Composer is never left running (ADR-010). The observability design distinguishes
"paused by design" from "stale" so teardown does not create false incidents.

## BigQuery (recovery + game-day queries)

- The QUARANTINE recovery removed 100 000 rows via two targeted `DELETE`s
  (raw + intermediate); DELETEs on small dev tables are inexpensive.
- Game-day diagnosis used `INFORMATION_SCHEMA.JOBS` and row-count aggregates —
  metadata and small scans.
- No full-refresh rebuild was performed during recovery (targeted repair,
  ADR-014), avoiding a full re-scan of history.

## Retention

- Audit tables (`recovery_actions`, `task_events`, `pipeline_runs`,
  `quality_results`, `monitor_evaluations`) are small and retained; they are the
  durable operational history and are not cost-significant.
- No new long-lived cloud resources were created by Sprint 6 beyond the two
  additive schema objects (a table + two columns).

## Net cost posture

Sprint 6 is cost-*reducing* in expectation: the guards prevent the most common
accidental-spend paths (unbounded backfills, unintended full refreshes,
unbounded scans), while the only material acceptance spend is the ephemeral
Composer window (single-digit dollars).
