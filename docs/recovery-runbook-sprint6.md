# Atlas Recovery Runbook (Sprint 6)

Companion to `docs/observability-runbook-sprint5.md` (detection and
diagnosis). This runbook covers what to *do* once a failure is diagnosed, and
how to prove the recovery worked. Model: ADR-014.

## The decision tree

```text
FAILURE DETECTED
│
├─ 1. Is canonical data corrupted?
│   │   (raw/fact/mart rows wrong, duplicated, or partially loaded — not
│   │    merely a failed run that published nothing)
│   │
│   ├─ NO ──► pick the cheapest state-restoring action:
│   │         • task failed transiently ............ RETRY_TASK
│   │         • run failed, data untouched ......... RERUN_BATCH (same batch id)
│   │         • permission removed ................. RESTORE_IAM (exact binding)
│   │         • bad release deployed ............... RESTORE_RELEASE (rollback path)
│   │         • monitor/alert state wrong .......... RESET_MONITOR
│   │
│   └─ YES ─► contain first, repair second:
│             a. PAUSE_SCHEDULE / block publication (no new consumers of bad data)
│             b. QUARANTINE_BATCH (isolate the affected batch identity)
│             c. determine the repair boundary (batch? partition? table?)
│             │
│             ├─ 2. Can the batch/partition be repaired safely?
│             │   ├─ YES ─► targeted repair:
│             │   │         REPAIR_PARTIAL_LOAD or REBUILD_PARTITION (bounded),
│             │   │         then reconcile, then RESUME_SCHEDULE
│             │   └─ NO ──► restore prior compatible runtime (RESTORE_RELEASE),
│             │             FORWARD_MIGRATION if schema demands it,
│             │             rebuild affected history, BACKFILL (bounded window),
│             │             reconcile, RESUME_SCHEDULE
```

Ordering rules:

- Targeted repair before rebuild; rebuild before restore-and-backfill.
- `dbt build --full-refresh` is never the first response — it is gated by
  `ATLAS_APPROVE_FULL_REFRESH` (S6-COST-003) precisely so nobody reaches for
  it reflexively.
- Backfills are bounded to the 7-day policy window;
  `ATLAS_APPROVE_UNBOUNDED_BACKFILL=true` requires a documented cost review
  (S6-COST-002).
- Rollback across a `breaking`-flagged migration is refused by the deploy
  engine (`ROLLBACK_INCOMPATIBLE`); recover forward (ADR-015).

## Recording the recovery

Every attempt gets a row in `atlas_ops.recovery_actions` **before** the
mutation starts:

```python
from atlas.ops.recovery_actions import start_recovery_action, finalize_recovery_action

rec = start_recovery_action(
    recovery_id="s6-<scenario>-<n>",
    action_type="RERUN_BATCH",
    scenario_id="S6-ING-001",
    incident_id="<monitoring incident id if any>",
    pipeline_run_id="...", batch_id="...", operator="russell",
    environment="atlas-dev", source_state="FAILED", target_state="SUCCESS",
)
# ... perform + verify ...
finalize_recovery_action(rec, status="SUCCESS", verification_status="VERIFIED")
```

`SUCCESS` without `VERIFIED` raises by design. A recovery that cannot pass
verification is finalized `PARTIAL` or `FAILED` — honestly.

## The verification list (all must pass before SUCCESS)

Run against the affected batch/partition:

1. raw count exact (generator contract: 50,000 per standard batch)
2. accepted + rejected = raw
3. classification count = raw
4. fact count = accepted
5. fact event_ids unique
6. fact foreign keys resolve (users, countries)
7. mart totals reconcile
8. success marker present (success path only)
9. `pipeline_runs` row terminal and truthful
10. `task_events` telemetry complete for the run
11. `recovery_actions` row finalized with verification
12. monitor evaluations return to PASS
13. related incident closed/resolved
14. zero duplicate rows anywhere in the lineage

Convenient wrapper: `scripts/atlas_step_runner.py validate_warehouse` with the
batch context executes checks 1–7 and persists them to
`atlas_ops.quality_results`.

## Reconstruction procedure (RECONSTRUCT_AUDIT)

When the finalizer or telemetry writes failed (S6-AIR-003, S6-OBS-002/008):

1. Collect ground truth: Airflow task instance states (`airflow tasks
   states-for-dag-run`), GCS object existence/generation, BigQuery row counts,
   any `task_events` rows that did land, structured logs in `atlas-events`.
2. Derive the run's true terminal status from data state, not from wishes:
   marker + reconciliation pass = SUCCESS; anything else = FAILED.
3. Upsert the corrected `pipeline_runs` row (idempotent MERGE keyed by
   `pipeline_run_id`) and the missing `task_events` rows with
   `timing_source='finalizer_reconciliation'` and honest
   `timing_confidence` (`partial` or `none` — never invented `exact`).
4. Record the RECONSTRUCT_AUDIT recovery action; verify telemetry
   completeness now passes; close the telemetry-incomplete incident.

## Per-category quick reference

| Diagnosis | First action | Verify with |
| --- | --- | --- |
| Missing/corrupt artifact | quarantine object, regenerate deterministically, rerun | checksum match + counts |
| Partial raw load | delete/replace only the affected batch partition rows, rerun load | exact count + uniqueness |
| Retry exhaustion | fix cause, rerun same batch id | full verification list |
| Worker interruption | let retry policy work; rerun if terminal | task_events attempts + counts |
| Finalizer failure | RECONSTRUCT_AUDIT (above) | completeness PASS |
| dbt test/RI/duplicate failure | quarantine offending rows (fixture or batch), rerun | dbt tests green + reconciliation |
| Incremental corruption | targeted partition rebuild in place | non-target partitions unchanged |
| IAM loss | restore the exact removed binding only | probe operation + policy diff vs baseline |
| Failed deployment/smoke | RESTORE_RELEASE to last SUCCESS deployment | rollback smoke 12/12 |
| Rollback failure | secondary RESTORE_RELEASE / forward fix | deployments audit + smoke |
| Cost guard trip | fix the query/window; never raise ceilings casually | dry-run estimate below ceiling |

## Escalation

Primary operator: the primary operator. Escalation: repository owner/designated
reviewer. External escalation only through the approved notification channel.
Preserve evidence before changing any firing policy or deleting any fixture.
