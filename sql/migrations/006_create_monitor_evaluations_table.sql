-- Migration 006 (Sprint 5, Phase 4): observability monitor evaluations.
-- Grain: one row per monitor check per evaluation window.
CREATE TABLE IF NOT EXISTS `atlas_ops.monitor_evaluations` (
  evaluation_id STRING NOT NULL,
  check_name STRING NOT NULL,
  environment STRING NOT NULL,
  window_start TIMESTAMP,
  window_end TIMESTAMP,
  status STRING NOT NULL,
  severity STRING,
  observed_value FLOAT64,
  threshold FLOAT64,
  incident_key STRING,
  source STRING,
  evaluated_at TIMESTAMP NOT NULL,
  details_json STRING,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
)
OPTIONS (
  description = 'Atlas observability monitor evaluations (Sprint 5). One row per monitor check per window — MERGE-idempotent on evaluation_id. Statuses: PASS, WARN, FAIL, NO_DATA, DISABLED.'
);
