-- Migration 007 (Sprint 6, Phase 4): recovery-action audit table.
-- Grain: one row per recovery action attempt, keyed by recovery_id.
-- Additive only — written via idempotent MERGE from atlas.ops.recovery_actions.
-- Recovery actions are a separate grain from pipeline_runs and deployments —
-- they link to those records but never mutate them.
CREATE TABLE IF NOT EXISTS `atlas_ops.recovery_actions` (
  recovery_id STRING NOT NULL,
  incident_id STRING,
  scenario_id STRING,
  pipeline_run_id STRING,
  batch_id STRING,
  deployment_id STRING,
  action_type STRING NOT NULL,
  operator STRING,
  environment STRING,
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  status STRING NOT NULL,
  source_state STRING,
  target_state STRING,
  verification_status STRING,
  error_type STRING,
  error_summary STRING,
  git_sha STRING,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
)
OPTIONS (
  description = 'Atlas recovery-action audit (Sprint 6). One row per recovery attempt — MERGE-idempotent — errors sanitized. Controlled action types: RETRY_TASK, RERUN_BATCH, REPAIR_PARTIAL_LOAD, QUARANTINE_BATCH, BACKFILL, RESTORE_RELEASE, FORWARD_MIGRATION, RESTORE_IAM, REBUILD_PARTITION, PAUSE_SCHEDULE, RESUME_SCHEDULE, RECONSTRUCT_AUDIT, RESET_MONITOR, MANUAL_CONTAINMENT. Statuses: RUNNING, SUCCESS, FAILED, PARTIAL, ABORTED. SUCCESS requires verification_status=VERIFIED.'
);
