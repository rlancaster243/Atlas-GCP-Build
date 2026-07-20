# Atlas Sprint 6 Failure Catalog

The machine-readable source of truth is `config/failure_scenarios.yaml`
(schema-validated by the `failure_injection` CI gate; 56 scenarios). This
document is the operator-facing index. Every scenario defines: category, risk
level, target component, preconditions, injection method, expected
detection/alert/containment, allowed data impact, recovery action,
verification queries, cleanup, recurrence prevention, required approvals, and
maximum duration/cost. See ADR-013 for the framework rules.

Execution modes: **unit** = proven by repository tests, **live** = requires
the game-day Composer window, **both** = unit-tested logic plus a live
demonstration.

## Ingestion (Game Day 1)

| ID | Failure | Risk | Mode | Recovery |
| --- | --- | --- | --- | --- |
| S6-ING-001 | Missing source artifact | LOW | live | RERUN_BATCH |
| S6-ING-002 | Corrupt JSONL | MEDIUM | live | QUARANTINE_BATCH → RERUN_BATCH |
| S6-ING-003 | Checksum conflict on immutable path | LOW | both | MANUAL_CONTAINMENT |
| S6-ING-004 | Partial raw load | HIGH | live | REPAIR_PARTIAL_LOAD |
| S6-ING-005 | Duplicate execution of same batch | MEDIUM | live | (idempotency expected) |
| S6-ING-006 | Transient GCS failure | LOW | live | RETRY_TASK |
| S6-ING-007 | Transient BigQuery failure | MEDIUM | unit | RETRY_TASK |
| S6-ING-008 | Retry exhaustion | MEDIUM | live | RERUN_BATCH |

## Orchestration (Game Day 3)

| ID | Failure | Risk | Mode | Recovery |
| --- | --- | --- | --- | --- |
| S6-AIR-001 | Worker interruption mid-task | MEDIUM | live | RETRY_TASK |
| S6-AIR-002 | Task timeout | LOW | live | RERUN_BATCH |
| S6-AIR-003 | Finalizer failure | HIGH | live | RECONSTRUCT_AUDIT |
| S6-AIR-004 | Overlapping runs | MEDIUM | live | (concurrency expected) |
| S6-AIR-005 | Invalid run context | LOW | both | MANUAL_CONTAINMENT |
| S6-AIR-006 | Scheduler interruption / missed run | MEDIUM | live | BACKFILL |

## Warehouse and dbt (Game Day 2)

| ID | Failure | Risk | Mode | Recovery |
| --- | --- | --- | --- | --- |
| S6-DBT-001 | Source freshness failure | LOW | live | BACKFILL |
| S6-DBT-002 | dbt test failure | LOW | live | RERUN_BATCH |
| S6-DBT-003 | Referential-integrity failure | MEDIUM | live (fixture) | QUARANTINE_BATCH |
| S6-DBT-004 | Duplicate fact event | MEDIUM | live (fixture) | REPAIR_PARTIAL_LOAD |
| S6-DBT-005 | Late-arriving events | MEDIUM | live | BACKFILL |
| S6-DBT-006 | Incremental target corruption | HIGH | live (fixture) | REBUILD_PARTITION |
| S6-DBT-007 | Partition rebuild | MEDIUM | live (fixture) | REBUILD_PARTITION |

## Schema evolution (Game Day 2)

| ID | Failure | Risk | Mode | Expected classification |
| --- | --- | --- | --- | --- |
| S6-SCH-001 | Approved nullable field | LOW | both | ALLOWED |
| S6-SCH-002 | Unapproved additive field | LOW | both | WARNING |
| S6-SCH-003 | Renamed field | MEDIUM | both | BREAKING (removed_field) |
| S6-SCH-004 | Removed field | MEDIUM | both | BREAKING |
| S6-SCH-005 | Incompatible type change | MEDIUM | both | BREAKING |
| S6-SCH-006 | Required-field change | HIGH | both | BREAKING |
| S6-SCH-007 | Partition-field change | HIGH | both | BREAKING (never auto-applied) |
| S6-SCH-008 | Multiple schema versions | MEDIUM | unit | normalized, no silent coercion |

## IAM (Game Day 3)

| ID | Failure | Risk | Mode | Recovery |
| --- | --- | --- | --- | --- |
| S6-IAM-001 | BigQuery job permission removal | HIGH | live | RESTORE_IAM |
| S6-IAM-002 | BigQuery data access removal | HIGH | live | RESTORE_IAM |
| S6-IAM-003 | GCS object permission removal | MEDIUM | live | RESTORE_IAM |
| S6-IAM-004 | Runtime permission vs code failure classification | MEDIUM | both | RESTORE_IAM |
| S6-IAM-005 | WIF authentication failure | MEDIUM | live | RESTORE_IAM |

All IAM scenarios: capture before/after policy, remove exactly one binding,
restore exactly that binding, verify effective access, `ATLAS_APPROVE_IAM`.

## Deployment and rollback (Game Day 4)

| ID | Failure | Risk | Mode | Recovery |
| --- | --- | --- | --- | --- |
| S6-DEP-001 | Broken DAG import | LOW | live | RESTORE_RELEASE |
| S6-DEP-002 | Incompatible dependency | MEDIUM | unit | RESTORE_RELEASE |
| S6-DEP-003 | Failed migration | MEDIUM | live | FORWARD_MIGRATION |
| S6-DEP-004 | Bundle checksum failure | LOW | both | RESTORE_RELEASE |
| S6-DEP-005 | Failed smoke run | MEDIUM | live | RESTORE_RELEASE |
| S6-DEP-006 | Schema/runtime incompatibility | MEDIUM | unit | FORWARD_MIGRATION |
| S6-RBK-001 | Missing rollback bundle | LOW | both | MANUAL_CONTAINMENT |
| S6-RBK-002 | Rollback smoke failure | HIGH | live | RESTORE_RELEASE (secondary) |
| S6-RBK-003 | Irreversible migration blocks rollback | MEDIUM | unit | FORWARD_MIGRATION |

## Observability degradation (Game Day 5)

| ID | Failure | Risk | Mode | Recovery |
| --- | --- | --- | --- | --- |
| S6-OBS-001 | Cloud Logging write failure | LOW | unit | RESET_MONITOR |
| S6-OBS-002 | task_event write failure | MEDIUM | live | RECONSTRUCT_AUDIT |
| S6-OBS-003 | Metric publication failure | LOW | unit | RESET_MONITOR |
| S6-OBS-004 | Monitor DAG failure | MEDIUM | live | RESET_MONITOR |
| S6-OBS-005 | Alert policy disabled unexpectedly | LOW | live | RESET_MONITOR |
| S6-OBS-006 | Notification channel failure | LOW | live | RESET_MONITOR |
| S6-OBS-007 | Linked log dataset unavailable | LOW | live | RESET_MONITOR |
| S6-OBS-008 | Terminal run with missing telemetry | MEDIUM | live | RECONSTRUCT_AUDIT |

Rule: observability failure must never erase evidence of the underlying
failure, and telemetry failure must never corrupt a successful data operation.

## Cost guardrails (validated without material spend)

| ID | Failure | Risk | Mode | Guard |
| --- | --- | --- | --- | --- |
| S6-COST-001 | Removed partition filter | LOW | both | dry-run byte ceiling (`enforce_dry_run_ceiling`) |
| S6-COST-002 | Unbounded backfill | LOW | unit | window guard in `resolve_run_context` |
| S6-COST-003 | Full refresh outside policy | LOW | unit | `ATLAS_APPROVE_FULL_REFRESH` gate in step runner |
| S6-COST-004 | Duplicate job submission | LOW | live | batch idempotency (bytes evidence) |
| S6-COST-005 | Query exceeds byte limit | LOW | both | `maximum_bytes_billed` job config |
