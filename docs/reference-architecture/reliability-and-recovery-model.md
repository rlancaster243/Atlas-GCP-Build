# Reliability and Recovery Model

**Status:** CURRENT · **Audience:** operator, reviewer. Authoritative detail:
[failure-catalog-sprint6.md](../failure-catalog-sprint6.md),
[recovery-runbook-sprint6.md](../recovery-runbook-sprint6.md),
[game-day-results-sprint6.md](../game-day-results-sprint6.md), ADR-013/014/015.

## Lifecycle

```
detect → contain → diagnose → recover → verify → prevent
```

- **Detect** — retries, dbt test failures, overlapping-run guards, cost-guard
  blocks surface via `task_events`/`pipeline_runs`/telemetry.
- **Contain** — failed runs publish no success marker (INV-L5); DAGs paused to
  stop scheduler contention; cost guards block before spend.
- **Diagnose** — root cause from `task_events`, `INFORMATION_SCHEMA.JOBS`, dbt
  output, row-count queries. Correlated by `pipeline_run_id`/`batch_id` (INV-O2).
- **Recover** — targeted repair (e.g. `QUARANTINE_BATCH`), not blanket full
  refresh; recorded in `atlas_ops.recovery_actions`.
- **Verify** — `validate_warehouse(<batch>)`; SUCCESS gated on `VERIFIED`
  (INV-O3). Proven live: INC-S6-001 recovered + verified 10/10.
- **Prevent** — documented follow-ups + regression tests + reusable controls.

## Idempotency, replay, backfills

- Exact rerun idempotent (INV-D3); within-batch dup vs cross-batch replay
  distinct (INV-D4, ADR-006 amendment resolved Sprint 6 INC-S6-001).
- Backfills deterministic (Sprint 3); global fact uniqueness preserved (INV-D5).

## Fault injection & rollback

- Fault injection disabled by default, gated (INV-O4, ADR-013).
- Rollback checks schema compatibility (INV-L6, ADR-015); a failed deployment
  cannot publish success (INV-L5).

## Known gaps (→ [unresolved-risks.md](unresolved-risks.md))

- Composer customer-project task-log limitation (Sprint 5) — mitigated by direct
  Cloud Logging export.
- Live game-day coverage is a representative subset; full live injection of all
  56 catalog scenarios was intentionally not performed.
- Synthetic 50k-row scale — reliability behavior is proven at that scale only.
