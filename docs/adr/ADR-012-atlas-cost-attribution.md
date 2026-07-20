# ADR-012: Atlas BigQuery Cost Attribution

Status: accepted (Sprint 5)
Date: 2026-07-19

## Context

Sprint 5 must answer "is delivery or warehouse cost behaving abnormally"
(mission question 6). BigQuery exposes job usage through region-qualified
`INFORMATION_SCHEMA.JOBS` (bytes processed/billed, slot ms, errors, labels,
identity), but only if Atlas jobs are distinguishable from everything else
in the project. Query-text matching is fragile and was rejected as a primary
strategy.

## Decision

Attribution evidence order (strongest first):

1. **Job labels** — every Atlas job carries
   `application=atlas, component=<bounded>, environment=atlas-dev`.
   - Python: `atlas.observability.cost.labeled_bigquery_client` sets the
     labels via the client's `default_query_job_config`; all Atlas modules
     (audit, task_events, quality_results, migrations, deployments,
     validation, loader, preflight, resources) create clients through it.
     Components are drawn from a bounded set
     (`pipeline, monitor, deployment, validation, audit, migration,
     ingestion, adhoc`); run/batch identifiers are excluded by design.
   - dbt: the officially supported `query-comment` + `job-label: true`
     configuration in `dbt_project.yml` converts a static JSON comment
     (`application=atlas, component=dbt, environment=atlas-dev`) into job
     labels. No dbt internals are patched.
2. **Runtime identity** — `atlas-composer-runtime`,
   `atlas-github-integration`, `atlas-github-deployer` service accounts
   (`user_email` in JOBS) catch anything that escaped labeling.
3. **Referenced/destination Atlas datasets** — forensic fallback only.

Canonical queries live in `observability/queries/bigquery_cost.sql`:
daily bytes processed/billed, slot ms, job failures, usage by component,
unusually expensive jobs, and a labeled-vs-identity trend that quantifies
attribution coverage. All queries exclude parent `SCRIPT` rows (double
counting) and bound `creation_time`.

The monitor DAG publishes windowed
`custom.googleapis.com/atlas/cost/bigquery_bytes_billed` and
`.../cost/bigquery_job_count` gauges from the same attribution and stores
evaluations in `atlas_ops.monitor_evaluations`. The cost-anomaly alert
compares the window against the configured baseline ratio
(`config/observability.yaml`); the cost drill uses a synthetic signal, never
a deliberately expensive query.

## Rules

- No full query text in Atlas operational tables (log/security hygiene).
- No `pipeline_run_id`/`batch_id` in job labels: cardinality is unnecessary
  because JOBS already timestamps every job and Plane 1 orders runs in time.
- On-demand pricing estimate (`$6.25/TiB`) is a planning heuristic, not a
  billing source; the Cloud Billing export remains authoritative for spend.

## Consequences

- Cost questions are answerable per day and per component with bounded
  scans (~180-day JOBS retention).
- Attribution coverage is itself measurable (query 6); a growing
  `unlabeled_jobs` count is a regression signal.
- Known gap: BigQuery jobs issued by third-party tools without labels or
  Atlas identities (e.g. ad-hoc console queries by humans) attribute only via
  dataset references; accepted for a development project.
