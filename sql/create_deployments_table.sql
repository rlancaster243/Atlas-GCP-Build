-- Deployment audit: one row per deployment or rollback attempt (Sprint 4, Phase 10).
CREATE TABLE IF NOT EXISTS `{project_id}.atlas_ops.deployments` (
  deployment_id STRING NOT NULL,
  git_sha STRING NOT NULL,
  git_ref STRING,
  release_tag STRING,
  environment STRING NOT NULL,
  workflow_run_id STRING,
  actor STRING,
  deployment_type STRING NOT NULL,
  started_at TIMESTAMP NOT NULL,
  completed_at TIMESTAMP,
  status STRING NOT NULL,
  artifact_uri STRING,
  artifact_checksum STRING,
  composer_environment STRING,
  composer_region STRING,
  smoke_pipeline_run_id STRING,
  previous_git_sha STRING,
  migration_count INT64,
  failure_stage STRING,
  error_type STRING,
  error_summary STRING,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
)
CLUSTER BY status, environment, git_sha;
