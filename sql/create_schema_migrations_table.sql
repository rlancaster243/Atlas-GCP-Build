-- Migration ledger: one row per applied schema migration (Sprint 4, Phase 9).
CREATE TABLE IF NOT EXISTS `{project_id}.atlas_ops.schema_migrations` (
  migration_id STRING NOT NULL,
  migration_checksum STRING NOT NULL,
  git_sha STRING,
  applied_at TIMESTAMP NOT NULL,
  workflow_run_id STRING,
  applied_by STRING,
  status STRING NOT NULL,
  error_summary STRING
)
CLUSTER BY migration_id;
