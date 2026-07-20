-- Operational metadata dataset for Project Atlas orchestration.
CREATE SCHEMA IF NOT EXISTS `{project_id}.atlas_ops`
OPTIONS (
  location = '{location}',
  description = 'Operational metadata and audit records for Project Atlas pipelines.'
);
