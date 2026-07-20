# Observability Model

**Status:** CURRENT · **Audience:** operator, reviewer. Authoritative detail:
[observability-runbook-sprint5.md](../observability-runbook-sprint5.md),
[alert-catalog-sprint5.md](../alert-catalog-sprint5.md), ADR-011/012.

## Layers

- **Durable audit** — `atlas_ops.{pipeline_runs,task_events,quality_results,
  monitor_evaluations,deployments,schema_migrations,recovery_actions}` (INV-O1).
- **Logs** — structured JSON to the `atlas-events` log with correlation ids
  (`pipeline_run_id`, `batch_id`), redaction, and truncation (INV-O2, INV-G8).
  Exported to a linked BigQuery dataset (`atlas_logs`) via a sink.
- **Metrics** — custom + log-based metrics (`observability/metrics/`), e.g.
  `custom.googleapis.com/atlas/pipeline/last_success_age_seconds`,
  `.../monitor/check_status`, `.../cost/bigquery_bytes_billed`.
- **Alerts** — Cloud Monitoring policies (`observability/alerts/*.json`), each
  mapped to a runbook section (INV-O6).
- **Dashboard** — operational dashboard (`observability/dashboards/`).

## Correlation & alert→runbook

Every telemetry event carries correlation ids so a single run's story is
queryable end-to-end (example query in [README.md](../../README.md) Sprint 5
section). Every alert maps to a runbook procedure; `gate_reference_handoff`
checks that alert definitions and runbook references stay consistent.

## Known behaviors and limitations

- **NO_DATA behavior** — some policies alert on absence (e.g. stale data); these
  are environment-dependent and are disabled during controlled teardown.
- **Composer customer-project task-log limitation** — task logs are not always
  fully available in the customer project; mitigated by direct Cloud Logging
  export set at environment-create time (`ATLAS_LOG_TO_CLOUD_LOGGING=true`).
- **Post-teardown behavior** — after ephemeral Composer teardown, environment
  -dependent alerts are disabled and permanent resources (audit tables, log
  bucket/sink/view, metric descriptors, non-environment alert policies,
  notification channel, dashboard) remain valid. Recorded in
  `validation-report-sprint6.md` §8.

These are honest operational limitations, tracked in
[unresolved-risks.md](unresolved-risks.md).
