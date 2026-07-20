# Atlas saved log queries (Sprint 5, Phase 5)

Cloud Logging filters for Logs Explorer scoped to the `atlas-observability`
bucket / `atlas-runtime` view (or project-wide before routing exists). All
structured Atlas contract events carry `jsonPayload.atlas_event=true` and the
correlation fields from ADR-011. Replace the example identifiers before use.

## 1. Everything for one pipeline run

```text
jsonPayload.pipeline_run_id="atlas-20260719T060000Z-abcd1234"
```

Airflow's own task logs for the same run (Composer resource logs keyed by the
Airflow run id):

```text
resource.type="cloud_composer_environment"
labels.workflow="atlas_batch_pipeline"
labels."run_id"="atlas-scheduled__2026-07-19T06:00:00+00:00"
```

## 2. One task attempt

```text
jsonPayload.pipeline_run_id="atlas-20260719T060000Z-abcd1234"
jsonPayload.task_id="load_bigquery_raw"
jsonPayload.attempt_number=2
```

Airflow-native equivalent:

```text
resource.type="cloud_composer_environment"
labels.workflow="atlas_batch_pipeline"
labels."task-id"="load_bigquery_raw"
labels."try-number"="2"
```

## 3. All Atlas failures

```text
jsonPayload.atlas_event=true
(jsonPayload.event_type="task_failed" OR jsonPayload.severity="ERROR" OR jsonPayload.severity="CRITICAL")
```

## 4. All retries

```text
jsonPayload.atlas_event=true
jsonPayload.event_type="task_retry"
```

## 5. One deployment

```text
jsonPayload.deployment_id="atlas-dev-20260719-abc123"
```

## 6. One rollback

```text
jsonPayload.atlas_event=true
jsonPayload.deployment_id="atlas-dev-20260719-rollback1"
```

(rollbacks share the deployment contract; `atlas_ops.deployments` rows with
`deployment_type="rollback"` give the ids)

## 7. DAG parse errors

```text
resource.type="cloud_composer_environment"
log_id("airflow-dag-processor-manager") OR log_id("dag-processor-manager")
severity>=ERROR
```

## 8. Missing / broken task telemetry

```text
jsonPayload.atlas_event=true
(jsonPayload.event_type="task_telemetry_write_failed" OR jsonPayload.event_type="telemetry_emit_failed" OR jsonPayload.event_type="quality_result_write_failed")
```

Durable completeness check (BigQuery, Plane 1):

```sql
-- Expected tasks lacking a terminal event for a run
SELECT task_id, ARRAY_AGG(event_type ORDER BY event_type) AS events
FROM `example-gcp-project.atlas_ops.task_events`
WHERE pipeline_run_id = @pipeline_run_id
GROUP BY task_id
HAVING COUNTIF(event_type IN ('SUCCESS','FAILED','SKIPPED','UPSTREAM_FAILED')) = 0;
```

## 9. High-duration tasks

```text
jsonPayload.atlas_event=true
jsonPayload.event_type="task_success"
jsonPayload.duration_ms>300000
```

Durable equivalent:

```sql
SELECT pipeline_run_id, task_id, attempt_number, duration_ms
FROM `example-gcp-project.atlas_ops.task_events`
WHERE event_type = 'SUCCESS'
  AND duration_ms > 300000
  AND created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
ORDER BY duration_ms DESC;
```

## Linked-dataset access (Log Analytics / BigQuery)

The linked read-only dataset `atlas_logs` exposes the bucket's `_AllLogs`
view. Example: correlate one run across Composer and Atlas events:

```sql
SELECT timestamp, severity,
       JSON_VALUE(json_payload, '$.event_type') AS event_type,
       JSON_VALUE(json_payload, '$.task_id') AS task_id
FROM `example-gcp-project.atlas_logs._AllLogs`
WHERE JSON_VALUE(json_payload, '$.pipeline_run_id') = @pipeline_run_id
  AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
ORDER BY timestamp;
```

Always bound `timestamp` — the log table is partitioned by time and unbounded
scans are the main linked-dataset cost risk.
