# Sprint 5 Architecture — Atlas Observability

The observability model (three planes, source-of-truth table, correlation
hierarchy, trust boundaries) is normative in
`adr/ADR-011-atlas-observability-model.md`. This document maps the model to
concrete components and flows.

## Component map

```text
                    ┌──────────────────────────────────────────────┐
                    │            Composer 3 (atlas-dev)            │
                    │  atlas_batch_pipeline   atlas_observability_ │
                    │  (business DAG)         monitor (read-only)  │
                    └──────┬───────────────────────┬───────────────┘
     structured JSON events│ (one contract:        │ evaluations + metrics
     to task stdout        │  atlas.observability. │
                           ▼  logging)             ▼
        ┌────────────────────────────┐   ┌──────────────────────────┐
        │ Plane 2: Cloud Logging     │   │ Plane 1: BigQuery        │
        │ sink: atlas-observability- │   │ atlas_ops.pipeline_runs  │
        │   sink → bucket            │   │ atlas_ops.task_events    │
        │ atlas-observability (30 d, │   │ atlas_ops.quality_results│
        │ Log Analytics) → view      │   │ atlas_ops.monitor_evals  │
        │ atlas-runtime → linked BQ  │   │ atlas_ops.deployments    │
        │ dataset atlas_logs (RO)    │   │ atlas_ops.schema_migr.   │
        └──────────────┬─────────────┘   └────────────┬─────────────┘
                       │ log-based /                  │ monitor reads
                       │ custom metrics               │ (bounded windows)
                       ▼                              ▼
        ┌──────────────────────────────────────────────────────────┐
        │ Plane 3: Cloud Monitoring                                │
        │ custom.googleapis.com/atlas/* metrics · dashboard        │
        │ atlas-operations · 10 alert policies · incidents         │
        │ → email channel 6567861337166986657 (verified operator)  │
        └──────────────────────────────────────────────────────────┘
```

## Event flow for one pipeline run

1. `resolve_run_context` establishes `pipeline_run_id`/`batch_id`; every
   subsequent structured event carries the correlation fields.
2. Each task attempt writes `task_events` rows (STARTED → SUCCESS/FAILED/
   RETRY/...) via idempotent MERGE and emits contract events to stdout.
3. `validate_warehouse` persists its per-check results to `quality_results`
   in addition to failing the task on FAIL.
4. `write_run_summary` finalizes `pipeline_runs` and verifies task-telemetry
   completeness (missing attempts are reported, not silently ignored).
5. The monitor DAG evaluates freshness/volume/rejection/schema/deployment/
   cost windows, writes `monitor_evaluations`, publishes metrics, and emits
   structured evaluation logs.
6. Alert policies watch the metrics; incidents route to the operator email
   channel; runbook paths are embedded in policy documentation.

## Repository layout (Sprint 5 additions)

```text

  src/atlas/observability/      logging.py · metrics.py · checks.py · schema_drift.py
  src/atlas/ops/                task_events.py · quality_results.py
  sql/migrations/               004_create_task_events_table.sql
                                005_create_quality_results_table.sql
                                006_create_monitor_evaluations_table.sql
  dags/atlas_observability_monitor.py
  config/observability.yaml
  observability/
    logging/                    log-bucket.json · log-view.json · sink-filter.txt
    metrics/                    metric-descriptors.json
    alerts/                     *.json (10 policies)
    dashboards/                 atlas-operations.json
    queries/                    saved log + cost queries
  scripts/
    bootstrap_observability.sh  (plan/apply/status)
    manage_atlas_alerts.sh      (plan/apply/enable/disable/status/test/delete-test-resources)
  docs/                          runbook · alert catalog · on-call model · reviews
```

## Deployment integration

The Sprint 4 delivery system is unchanged: the deployment bundle gains the
monitor DAG, observability modules, config, and migrations 004–006; the same
`deploy_atlas_release.sh` → smoke → audit path promotes them. No second
deployment system exists. CI gains static gates for observability artifacts
(YAML/JSON validation, monitor DAG import, redaction and cardinality tests)
and stays credentialless on pull requests.

## Failure-visibility rules

- Telemetry failure degrades visibly (fallback `telemetry_emit_failed`
  events, `atlas/pipeline/telemetry_incomplete` metric) and never converts a
  successful data operation into a failure.
- Monitor no-data states are explicit (`NO_DATA` evaluations) and
  distinguished from `DISABLED` (`monitoring_enabled=false`, set before
  intentional teardown so absence alerts do not fire).
- The dashboard's top row answers "is Atlas healthy" in under a minute:
  latest run outcome, freshness age, open incidents, latest deployment.
