-- Migration 004 (Sprint 5, Phase 3): task-attempt audit table.
-- Grain: one row per (pipeline_run_id, task_id, attempt_number, event_type).
-- Additive only — written via idempotent MERGE from atlas.ops.task_events.
CREATE TABLE IF NOT EXISTS `atlas_ops.task_events` (
  pipeline_run_id STRING NOT NULL,
  batch_id STRING,
  airflow_run_id STRING,
  dag_id STRING,
  task_id STRING NOT NULL,
  attempt_number INT64 NOT NULL,
  event_type STRING NOT NULL,
  status STRING,
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  duration_ms INT64,
  operator_type STRING,
  environment STRING,
  git_sha STRING,
  rows_affected INT64,
  error_type STRING,
  error_message STRING,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
)
OPTIONS (
  description = 'Atlas task-attempt audit (Sprint 5). One row per task attempt event — MERGE-idempotent — errors sanitized. Controlled event types: STARTED, RETRY, SUCCESS, FAILED, SKIPPED, UPSTREAM_FAILED.'
);
