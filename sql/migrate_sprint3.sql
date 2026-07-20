-- Sprint 3 additive migration for stable batch identity on raw events.
-- Existing Sprint 1 rows remain batch_id = NULL.

ALTER TABLE `{project_id}.{dataset_id}.events`
ADD COLUMN IF NOT EXISTS batch_id STRING
OPTIONS (
  description = 'Stable logical batch identifier used for idempotency, reruns, and backfills.'
);

-- Logical batch processing date. Drives reproducible, ingestion-independent
-- temporal anomaly flags so historical backfills classify identically to the
-- original run (see ADR-003). Legacy Sprint 1 rows remain NULL and fall back to
-- DATE(ingested_at) in staging.
ALTER TABLE `{project_id}.{dataset_id}.events`
ADD COLUMN IF NOT EXISTS processing_date DATE
OPTIONS (
  description = 'Logical batch processing date for reproducible temporal semantics.'
);
