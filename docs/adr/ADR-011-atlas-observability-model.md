# ADR-011: Atlas Observability Model (Three Planes)

Status: accepted (Sprint 5)
Date: 2026-07-19
Owner: the primary operator (primary operator)

## Context

Sprints 1–4 produced durable *audit* records (`atlas_ops.pipeline_runs`,
`atlas_ops.deployments`, `atlas_ops.schema_migrations`) but no centralized
logs, no metrics, no alerting, and no dashboard. Sprint 4 live acceptance
additionally proved a real defect: Composer 3 task/worker logs never reached
Cloud Logging in this project (see `preflight-sprint5.md` §4), forcing
diagnosis through the Airflow REST API. Operators need to answer "did it
run, where is it failing, is the data correct and fresh, what did it cost,
who was told, and what do I do" from durable, queryable surfaces.

## Decision

Atlas observability uses three deliberately separate planes. No plane
imitates another; every signal declares one source of truth.

### Plane 1 — Operational audit (BigQuery, `atlas_ops`)

Durable, queryable history at controlled grains:

| Table | Grain | Source of truth for |
|---|---|---|
| `pipeline_runs` | one row per pipeline run | run status, row counts, freshness |
| `task_events` (new, 004) | one row per task attempt event | task-level diagnosis, retries, telemetry completeness |
| `quality_results` (new, 005) | one row per check per run | data correctness evidence |
| `monitor_evaluations` (new, 006) | one row per monitor check per window | monitor history, drill evidence |
| `deployments` | one row per deploy/rollback attempt | delivery status |
| `schema_migrations` | one row per migration | schema history |

### Plane 2 — Logs (Cloud Logging, Atlas-dedicated)

Cloud Logging stores high-cardinality, high-detail events: Airflow task
output, scheduler/worker/DAG-processor activity, structured Atlas
application events (one JSON contract, ADR §logging), deployment/rollback
events, monitor evaluations, and drill markers. Routing:

```text
project logs → sink atlas-observability-sink → log bucket atlas-observability
  (30-day retention, Log Analytics enabled) → view atlas-runtime
  → linked read-only BigQuery dataset atlas_logs
```

The `_Default` bucket keeps receiving source logs (the Atlas sink is
additive; no exclusion filters are added), so nothing is lost if the Atlas
bucket is misconfigured.

### Plane 3 — Metrics and incidents (Cloud Monitoring)

Low-cardinality time series (`custom.googleapis.com/atlas/<domain>/<metric>`),
dashboards, alert policies, incident lifecycle, and notification routing to
the verified operator email channel. Metric labels are bounded to:
`environment, dag_id, task_id, component, status, check_name, severity`.
Run/batch/deployment identifiers and raw error strings are **forbidden** as
metric labels; they live in Planes 1–2 and are joined via time + labels.

## Source-of-truth declarations

| Question | Source of truth |
|---|---|
| Did the run succeed? | `atlas_ops.pipeline_runs` |
| Which task failed, which attempt? | `atlas_ops.task_events` + structured logs |
| Is the data correct? | `atlas_ops.quality_results` (dbt/warehouse evidence linked) |
| Is the data fresh? | latest SUCCESS in `pipeline_runs`; surfaced as `atlas/pipeline/last_success_age_seconds` |
| Did the deployment work? | `atlas_ops.deployments` |
| Is something wrong *right now*? | Cloud Monitoring incidents |
| Detailed history / forensics | `atlas-observability` log bucket (via `atlas_logs`) |
| What did it cost? | region-qualified `INFORMATION_SCHEMA.JOBS` (ADR-012) |

## Correlation hierarchy

```text
deployment_id → airflow_run_id → pipeline_run_id → batch_id → task_id → attempt_number
```

Every structured event carries the identifiers that exist at its scope; the
logging contract (Phase 2) enforces field names so one log filter follows a
run across planes.

## Trust boundaries, retention, degradation

- **Telemetry must never corrupt data processing**: audit/metric/log write
  failures emit a fallback structured error and degrade visibly (telemetry
  completeness monitor) but do not fail a task that moved data correctly —
  except the finalizer, which reports incomplete telemetry explicitly.
- **Retention**: Atlas log bucket 30 days (measured MB/day scale; revisit
  with real volume). `atlas_ops` tables are permanent (MB scale). Metric
  retention follows Cloud Monitoring defaults.
- **Access boundary**: linking `atlas_logs` into BigQuery extends log read
  access to BigQuery IAM; the linked dataset is read-only and the log view
  is least-privileged. Documented in `security-review-sprint5.md`.
- **Intentional teardown**: `monitoring_enabled=false` in
  `config/observability.yaml` (and disabled alert policies) precedes
  Composer deletion so absence-based alerts do not fire on an intentionally
  absent environment. Disabled runtime is distinguishable from stale runtime.

## Alternatives considered

- **Everything in BigQuery** (logs as rows): rejected — loses Cloud Logging
  ingestion, filters, retention control, and Monitoring integration; invites
  unbounded scans.
- **Everything in Cloud Monitoring** (audit as metrics): rejected — metric
  cardinality explodes with per-run identifiers and history is lossy.
- **Third-party observability stack**: out of scope by charter.

## Consequences

- Operators get one place per question, with correlation identifiers
  bridging planes.
- Costs stay near zero at rest (clean-slate project; measured baselines in
  `cost-review-sprint5.md`).
- The Sprint 4 missing-logs defect becomes a first-class acceptance gate:
  Plane 2 is only claimed after live retrieval of Composer task logs through
  the documented filters.
