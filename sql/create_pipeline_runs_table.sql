-- One row per Airflow DAG execution, keyed by pipeline_run_id.
CREATE TABLE IF NOT EXISTS `{project_id}.atlas_ops.pipeline_runs` (
  pipeline_run_id STRING NOT NULL,
  batch_id STRING NOT NULL,
  airflow_run_id STRING NOT NULL,
  dag_id STRING NOT NULL,
  processing_date DATE NOT NULL,
  started_at TIMESTAMP NOT NULL,
  completed_at TIMESTAMP,
  status STRING NOT NULL,
  attempt_number INT64,
  gcs_uri STRING,
  rows_generated INT64,
  rows_loaded INT64,
  rows_accepted INT64,
  rows_rejected INT64,
  fact_rows INT64,
  mart_event_count INT64,
  failed_task_id STRING,
  error_type STRING,
  error_message STRING,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
)
PARTITION BY processing_date
CLUSTER BY status, batch_id, dag_id;
