# ADR-014: Recovery Action Model

Status: Accepted (Sprint 6)

## Context

Sprint 3–5 record what *happened* (pipeline runs, deployments, task events,
quality results, monitor evaluations). They do not record what an operator
*did about it*. Without a durable recovery grain, "we recovered" is a claim
with no evidence, and repeated incidents cannot be compared.

## Decision

1. **Separate grain.** `atlas_ops.recovery_actions` stores one row per
   recovery action attempt, keyed by `recovery_id` and written with
   idempotent MERGE (migration 007). Recovery actions link to incidents,
   scenarios, pipeline runs, batches, and deployments — they never mutate
   those records and are never mixed into `pipeline_runs`.
2. **Controlled vocabulary.** Action types are the fixed set
   RETRY_TASK, RERUN_BATCH, REPAIR_PARTIAL_LOAD, QUARANTINE_BATCH, BACKFILL,
   RESTORE_RELEASE, FORWARD_MIGRATION, RESTORE_IAM, REBUILD_PARTITION,
   PAUSE_SCHEDULE, RESUME_SCHEDULE, RECONSTRUCT_AUDIT, RESET_MONITOR,
   MANUAL_CONTAINMENT. Statuses: RUNNING, SUCCESS, FAILED, PARTIAL, ABORTED.
3. **Verification is the recovery.** A recovery row can only be finalized
   SUCCESS with `verification_status=VERIFIED`; the module raises otherwise.
   The verification contract is the Phase 13 reconciliation list (raw,
   accepted, rejected, classification, fact, mart counts, uniqueness,
   referential integrity, success marker, audits, monitor state, incident
   resolution, no duplicates). PARTIAL and FAILED recoveries are first-class
   recorded outcomes, not embarrassments to be overwritten.
4. **Decision tree first.** `docs/recovery-runbook-sprint6.md` defines the
   choice order: (1) is canonical data corrupted? If no — retry, rerun,
   restore permission/release. If yes — pause publication, quarantine,
   determine repair boundary; targeted repair before rebuild, rebuild before
   restore-and-backfill. Full refresh is never the first response
   (enforced by the `ATLAS_APPROVE_FULL_REFRESH` cost guard).
5. **Sanitized like everything else.** `error_summary` passes through the
   Sprint 4 sanitizer; no secrets, no unbounded stack traces.

## Consequences

- Every game-day recovery leaves a queryable audit row with timing evidence
  for MTTR measurement.
- "Recovery succeeded" is machine-checkable: `status='SUCCESS'` implies a
  verification pass by construction.
