-- Migration 005 (Sprint 5, Phase 4): durable data-quality check results.
-- Grain: one row per data-quality check per pipeline run.
CREATE TABLE IF NOT EXISTS `atlas_ops.quality_results` (
  pipeline_run_id STRING NOT NULL,
  batch_id STRING,
  check_name STRING NOT NULL,
  check_category STRING NOT NULL,
  severity STRING NOT NULL,
  status STRING NOT NULL,
  observed_value FLOAT64,
  expected_value FLOAT64,
  lower_bound FLOAT64,
  upper_bound FLOAT64,
  evaluated_at TIMESTAMP NOT NULL,
  model_name STRING,
  details_json STRING,
  git_sha STRING,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
)
OPTIONS (
  description = 'Atlas data-quality results (Sprint 5). One row per check per pipeline run — MERGE-idempotent on (pipeline_run_id, check_name). Categories: FRESHNESS, COMPLETENESS, UNIQUENESS, REFERENTIAL_INTEGRITY, SCHEMA, VOLUME, REJECTION_RATE, RECONCILIATION.'
);
