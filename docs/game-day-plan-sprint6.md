# Atlas Sprint 6 Game-Day Plan

Five game days executed inside one ephemeral Composer window (target ≤ 12 h
total). Every scenario follows the lifecycle
`plan → run → observe → contain → diagnose → recover → verify → cleanup` via
`scripts/run_failure_scenario.sh`, with recovery rows in
`atlas_ops.recovery_actions` and timings captured for MTTR.

Per game day we record: detection time, diagnosis time, containment time,
recovery time, verification time, total MTTR, operator actions, failed
runbook steps, repeated manual work, missing evidence.

## Preconditions (all game days)

- Sprint 6 candidate release deployed and smoke-validated (12/12)
- Baseline healthy batch reconciled
- Alert policies enabled (including re-enabling `Atlas: data stale` and
  `Atlas: Composer environment unhealthy` disabled at Sprint 5 teardown)
- Approvals exported for the window; `ATLAS_INJECTION_SCENARIO` set per
  scenario and unset immediately after
- All drill batches use the `atlas-s6-` prefix

## Game Day 1 — Ingestion and idempotency

| Order | Scenario | Proof obligation |
| --- | --- | --- |
| 1 | S6-ING-002 corrupt JSONL | invalid artifact preserved, no publication, sanitized error |
| 2 | S6-ING-004 partial raw load | partial state detected, targeted repair, exact counts, no duplicates |
| 3 | S6-ING-005 duplicate execution | idempotency: counts unchanged, facts unique, two run rows |
| 4 | S6-ING-006 transient failure | RETRY task event then SUCCESS |
| 5 | S6-ING-001 missing artifact + S6-ING-003 checksum conflict | fail-safe boundary + immutability |
| 6 | S6-ING-008 retry exhaustion | terminal FAILED, downstream blocked, recovery rerun |

## Game Day 2 — Warehouse and schema

| Order | Scenario | Proof obligation |
| --- | --- | --- |
| 1 | S6-DBT-002 dbt test failure | publication blocked, incident, clean rerun |
| 2 | S6-DBT-003 referential failure (fixture) | failing rows traceable, canonical untouched |
| 3 | S6-DBT-004 duplicate fact (fixture) | grain protected |
| 4 | S6-DBT-005 late-arriving events | bounded backfill, history byte-identical, no duplicates |
| 5 | S6-DBT-006 incremental corruption (fixture) | targeted repair, not full refresh |
| 6 | S6-DBT-007 partition rebuild (fixture) | only intended partition changes |
| 7 | S6-SCH-001…007 against fixture table | correct ALLOWED/WARNING/BREAKING classifications live |

## Game Day 3 — IAM and orchestration

| Order | Scenario | Proof obligation |
| --- | --- | --- |
| 1 | S6-IAM-001 job permission loss | exact permission identified, least-privilege restore |
| 2 | S6-IAM-002 data access loss | clear boundary failure, no partial publication |
| 3 | S6-IAM-003 GCS permission loss | no unsafe fallback destination |
| 4 | S6-ING-008-style retry exhaustion under IAM denial (S6-IAM-004 evidence) | IAM vs code classification |
| 5 | S6-AIR-001 worker interruption | retryable, no duplication |
| 6 | S6-AIR-002 task timeout | classified, downstream blocked |
| 7 | S6-AIR-003 finalizer failure | RECONSTRUCT_AUDIT recovers truth |
| 8 | S6-AIR-004 overlapping runs / S6-AIR-005 invalid context | concurrency + pre-mutation failure |
| 9 | S6-AIR-006 missed run | stale detection, bounded backfill |

## Game Day 4 — Deployment and rollback

| Order | Scenario | Proof obligation |
| --- | --- | --- |
| 1 | S6-DEP-003 failed migration | ledger FAILED, promotion stops |
| 2 | S6-DEP-004 checksum conflict | immutable bundle preserved |
| 3 | S6-DEP-005 failed smoke | deployments FAILED, no promotion |
| 4 | S6-RBK-001 missing bundle | fails before mutation |
| 5 | S6-RBK-002 rollback smoke failure | ROLLBACK_FAILED + incident + secondary recovery |
| 6 | restore validated release | final SUCCESS deployment |

(S6-DEP-001/002/006 and S6-RBK-003 are covered by CI gates and unit tests;
S6-IAM-005 executes with Game Day 3's IAM window when workflow-side evidence
is practical.)

## Game Day 5 — Observability degradation

| Order | Scenario | Proof obligation |
| --- | --- | --- |
| 1 | S6-OBS-002 task-event write failure | data survives, completeness detects, reconstruction |
| 2 | S6-OBS-008 missing telemetry on terminal run | telemetry-incomplete alert + reconstruction |
| 3 | S6-OBS-004 monitor DAG failure | monitor outage visible, business audit intact |
| 4 | S6-OBS-005 unexpected policy disablement | governance check catches drift |
| 5 | S6-OBS-006 notification failure | incident truth without delivery, honest evidence |
| 6 | S6-OBS-007 linked dataset fallback | Cloud Logging as source of truth |
| 7 | S6-COST-001/004/005 live legs | guard evidence with zero material spend |

## Exit criteria (before teardown)

- final healthy batch reconciles 10/10
- zero unresolved test incidents
- `recovery_actions` has a verified row for every recovery performed
- all injection variables unset; drill fixtures deleted
- alert policies restored to repo-defined state, then teardown set disabled
- Composer deleted under `ATLAS_APPROVE_TEARDOWN`, no false alerts after
