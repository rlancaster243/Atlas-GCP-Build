# Atlas Observability Runbook (Sprint 5)

Operator procedures for every Atlas alert. Each alert policy links to its
section anchor here. Shared context first, then one section per alert.

Primary operator: the primary operator. Escalation: repository owner /
designated reviewer (see `on-call-model-sprint5.md`).

## The five questions, answered generically

| Question | Where to look |
|---|---|
| Did the pipeline run? | `atlas_ops.pipeline_runs` (latest row), dashboard top row |
| Is the data correct? | `atlas_ops.quality_results` for the run's `pipeline_run_id` |
| Who was alerted? | Cloud Monitoring incident → policy → channel "Atlas Primary Operator (email)" |
| How is it recovered? | Per-alert section below; usually rerun via `scripts/run_airflow_sprint3.sh` or redeploy/rollback via Sprint 4 workflows |
| How is recurrence prevented? | Convert the root cause into a regression test, alert change, or ADR amendment; record in the incident report |

## Shared first moves (any Atlas incident)

1. Open the **Atlas Operations** dashboard; the top row shows latest run,
   freshness age, deployment state, and Composer health at a glance.
2. Identify the run:

```sql
SELECT pipeline_run_id, batch_id, status, started_at, completed_at,
       rows_loaded, rows_accepted, rows_rejected
FROM `example-gcp-project.atlas_ops.pipeline_runs`
ORDER BY started_at DESC LIMIT 5;
```

3. Pull correlated logs (Logs Explorer, bucket `atlas-observability`, view
   `atlas-runtime`): `jsonPayload.pipeline_run_id="<id>"`. More filters in
   `observability/queries/log-filters.md`.
4. Preserve evidence **before** changing anything: incident ID, evaluation
   rows, log query links, relevant audit rows.

---

## Alert: atlas pipeline failed

- **Meaning**: latest `pipeline_runs` row is FAILED. Severity: critical.
- **Likely causes**: dbt test failure (including deliberate injection), GCP
  permission loss, BigQuery quota, task crash, upstream generation defect.
- **First query**: shared query above; then task diagnosis:

```sql
SELECT task_id, attempt_number, event_type, status, error_type, error_message
FROM `example-gcp-project.atlas_ops.task_events`
WHERE pipeline_run_id = '<id>' ORDER BY task_id, attempt_number;
```

- **First log filter**: `jsonPayload.pipeline_run_id="<id>" severity>=ERROR`
- **Containment**: nothing automatic mutates on failure; the DAG chain stops
  before `publish_success_marker`. Do not delete data.
- **Recovery**: fix the root cause, then rerun the batch
  (`scripts/run_airflow_sprint3.sh` or Airflow UI trigger with the same
  `batch_id` conf for an idempotent rerun — raw loading is create-only per
  batch and dbt is batch-scoped).
- **When NOT to rerun**: if the failure is in `validate_warehouse`
  reconciliation, diagnose first — rerunning on top of inconsistent state
  reproduces the failure and wastes evidence freshness.
- **Backfill safety**: backfills are safe for past `processing_date`s
  (Sprint 3 semantics); never backfill over a batch under investigation.
- **Verification**: rerun reaches SUCCESS, `quality_results` all PASS,
  incident auto-closes within ~40 min (next monitor cycle + auto-close).
- **Prevention**: add the failure mode to dbt tests or warehouse checks.

## Alert: atlas data stale

- **Meaning**: age since last SUCCESS exceeded 50 h. Severity: critical.
- **Likely causes**: DAG paused unintentionally, scheduler dead, repeated
  run failures (check the pipeline-failed alert first), Composer deleted
  without disabling monitoring.
- **First query**: freshness evaluation history:

```sql
SELECT evaluated_at, status, observed_value, threshold
FROM `example-gcp-project.atlas_ops.monitor_evaluations`
WHERE check_name = 'freshness' ORDER BY evaluated_at DESC LIMIT 10;
```

- **First log filter**: `resource.type="cloud_composer_environment" log_id("airflow-scheduler") severity>=ERROR`
- **Containment/recovery**: unpause the DAG or trigger a manual run; if the
  environment was intentionally torn down, set `monitoring_enabled: false`
  and disable this policy instead of chasing a ghost.
- **Verification**: next monitor cycle publishes PASS; incident closes.
- **Prevention**: the teardown checklist (Phase 15) disables absence-prone
  alerts before deletion.

## Alert: atlas reconciliation failed

- **Meaning**: FAIL rows exist in `quality_results` for the latest run.
- **Likely causes**: duplicate loads, dbt model regression, partial batch,
  manual mutation of warehouse tables.
- **First query**:

```sql
SELECT check_name, status, observed_value, expected_value, details_json
FROM `example-gcp-project.atlas_ops.quality_results`
WHERE pipeline_run_id = '<id>' AND status = 'FAIL';
```

- **Audit tables**: `quality_results`, then the specific warehouse tables
  named by the failing check.
- **Recovery**: never edit warehouse rows by hand. Fix the transformation
  and rerun the batch; dbt rebuilds are idempotent per batch.
- **When a backfill is safe**: only after the failing check passes on a
  fresh run of the current release.
- **Prevention**: promote the broken invariant into a dbt test.

## Alert: atlas volume deviation

- **Meaning**: latest raw rows deviate ≥ 80 % from the 7-run baseline.
- **Likely causes**: generator config change, truncated upload, duplicate
  batch, intentional batch-size change without threshold retuning.
- **First query**: `SELECT rows_loaded FROM ... pipeline_runs ORDER BY started_at DESC LIMIT 8;`
- **Recovery**: if the change is legitimate, update `volume` thresholds in
  `config/observability.yaml` with the new baseline (documented commit); if
  not, treat as a pipeline defect and rerun after diagnosis.
- **Prevention**: batch-size changes must land with a threshold update.

## Alert: atlas schema drift

- **Meaning**: live INFORMATION_SCHEMA diverges from the governed manifest
  with a BREAKING classification (removed/renamed field, type change,
  required-field loss, partition change).
- **First command**: `PYTHONPATH=src python -m atlas.observability.schema_drift --check`
- **Audit tables**: `schema_migrations` (was there an unrecorded change?).
- **Containment**: stop deployments (`atlas-deploy` workflow) until resolved.
- **Recovery**: restore the contract via an additive migration, or — for an
  approved intentional change — regenerate the manifest
  (`--generate`, review, commit) and ship it with the migration.
- **When not to rerun**: pipeline reruns cannot fix schema drift; do not
  rerun to "see if it clears".
- **Prevention**: schema changes only via the migration ledger + manifest
  regeneration in the same PR (CI gate checks the manifest parses).

## Alert: atlas deployment failed

- **Meaning**: latest `deployments` row is FAILED/ROLLBACK_FAILED.
- **First query**:

```sql
SELECT deployment_id, status, failure_stage, error_summary, git_sha
FROM `example-gcp-project.atlas_ops.deployments`
ORDER BY started_at DESC LIMIT 3;
```

- **First log filter**: `jsonPayload.deployment_id="<id>"`
- **Recovery**: per Sprint 4 runbook (`ci-cd-runbook-sprint4.md`) —
  `failure_stage` names the failed stage; fix and redeploy, or roll back to
  the previous validated release (`scripts/rollback_atlas.sh`).
- **Evidence**: keep the FAILED row and workflow logs; they are the audit.

## Alert: atlas rollback failed

- **Meaning**: ROLLBACK_FAILED — the safety net itself failed. Severity:
  critical, highest urgency.
- **First moves**: same queries as deployment failed; additionally verify
  what is actually running: `data/current/release-manifest.json`
  in the Composer bucket vs `atlas_ops.deployments`.
- **Containment**: freeze all deployment activity; the environment state is
  now unverified.
- **Recovery**: manual re-promotion of the last SUCCESS release bundle
  (verify checksums first via `lib_atlas_deploy.sh` helpers), then a manual
  smoke batch, then a corrected `deployments` record.
- **Escalation**: this is the one alert where the escalation contact should
  be engaged immediately if the first recovery attempt fails.

## Alert: atlas composer unhealthy

- **Meaning**: native `environment/healthy` fraction < 0.5 for 15 min.
- **Likely causes**: scheduler crash-loop, worker OOM, GKE node pressure,
  or (expected) creation/deletion transitions.
- **First look**: Composer environment page; then
  `resource.type="cloud_composer_environment" severity>=ERROR` logs.
- **Containment**: do not deploy onto an unhealthy environment.
- **Recovery**: Composer 3 self-heals most component failures; if unhealthy
  persists > 1 h, capture logs and recreate the ephemeral environment
  (`scripts/manage_atlas_composer.sh`).
- **Teardown note**: DISABLE this policy before intentional deletion.

## Alert: atlas cost anomaly

- **Meaning**: Atlas-attributed bytes billed in 24 h ≥ 10× the 7-day daily
  baseline and above the 1 GiB floor. Severity: warning.
- **First query**: `observability/queries/bigquery_cost.sql` queries 1, 4,
  and 5 (daily usage, by component, expensive jobs).
- **Likely causes**: unbounded monitor query regression, repeated backfills,
  a new query pattern missing partition filters.
- **Containment**: pause the offending component (monitor DAG or pipeline)
  if a runaway query loop is confirmed.
- **Recovery**: fix the query pattern; verify the next window's bytes fall
  back under threshold.
- **Never**: run a large query "to test" this alert — use
  `manage_atlas_alerts.sh test cost_anomaly` (synthetic signal).

## Alert: atlas telemetry incomplete

- **Meaning**: expected tasks lack terminal `task_events` rows for the
  latest run — observability is degraded even though the data may be fine.
- **First query**: the completeness SQL in
  `observability/queries/log-filters.md` §8.
- **First log filter**: `jsonPayload.event_type="task_telemetry_write_failed"`
- **Likely causes**: BigQuery audit-write outage, IAM regression on the
  runtime SA, a task crash before the telemetry wrapper ran, or runs
  predating Sprint 5 telemetry.
- **Recovery**: fix the write path; telemetry backfills automatically on the
  next run (per-run grain). Do not fabricate historical task events.
- **Important**: data correctness is judged by `quality_results`, not by
  telemetry presence — check reconciliation before treating this as a data
  incident.
