-- Project Atlas raw events table DDL.
-- Partitioned by event_date and clustered by event_name, country_code.
-- Metadata columns support lineage and idempotent run tracking.

CREATE TABLE IF NOT EXISTS `{project_id}.{dataset_id}.{table_id}` (
  event_id STRING NOT NULL,
  user_id STRING,
  event_name STRING NOT NULL,
  event_timestamp TIMESTAMP NOT NULL,
  event_date DATE NOT NULL,
  country_code STRING,
  platform STRING,
  app_version STRING,
  ingested_at TIMESTAMP NOT NULL,
  source_file STRING NOT NULL,
  pipeline_run_id STRING NOT NULL,
  batch_id STRING,
  processing_date DATE
)
PARTITION BY event_date
CLUSTER BY event_name, country_code;
