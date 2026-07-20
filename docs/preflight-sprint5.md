# Sprint 5 Preflight — Observability, Alerting, and Incident Readiness

Inspection completed 2026-07-19 ~02:45 UTC, before any Sprint 5 resource
creation. Every fact below was verified live against the repository, GitHub,
and GCP project `example-gcp-project`.

## 1. Git and release state

| Item | Value |
|---|---|
| PR #18 | verified (docs-only: `README.md`, `validation-report-sprint4.md`), marked ready, **squash-merged** as `45543b6` under `ATLAS_APPROVE_PR18_MERGE` |
| Current `origin/main` | `45543b6` (clean tree) |
| Sprint tags | 1: `270e7d5` · 2: `5135778` · 3: `8aa1d7a` · 4: **`b609ac1`** (verified resolves to PR #17 merge commit) |
| Sprint 5 branch | `cursor/atlas-sprint-5-observability-64a2` from `45543b6` |
| Open Atlas PRs | none (PRs #2, #3, #6 are unrelated pre-Atlas scaffolding) |
| CI | `atlas-ci.yml` green on last code merge; PR #18 was docs-only (path-filtered, no checks — expected) |

## 2. Current observability inventory (repository)

| Asset | State |
|---|---|
| `src/atlas/logging/structured.py` | JSON formatter + `StepLogger` context manager; writes local JSONL per run; fields are ad-hoc per call site, no enforced contract, no correlation hierarchy |
| `dags/atlas_orchestration/callbacks.py` | `on_retry_callback` / `on_failure_callback` print structured JSON to task stdout; nothing durable |
| Run summary | `write_run_summary` task writes local `run-summary.json` + finalizes `atlas_ops.pipeline_runs` (MERGE, sanitized errors) |
| `atlas_ops.pipeline_runs` | run grain; has rows_generated/loaded/accepted/rejected, fact_rows, mart_event_count, failed_task_id, error fields — good base for freshness/volume monitors |
| `atlas_ops.deployments` | attempt grain with failure_stage; 9 Sprint 4 rows |
| `atlas_ops.schema_migrations` | ledger; 3 APPLIED |
| Task-attempt audit | **does not exist** (no task_events table) |
| Quality results | **not durable** — warehouse reconciliation prints PASS/FAIL JSON only |
| `src/atlas/validation/warehouse.py` | 10 batch-scoped checks returning `WarehouseReport` — ready to persist into `quality_results` |

## 3. Current GCP observability state (all clean slate)

| Surface | Finding |
|---|---|
| Log buckets | only `_Default` (30 d) and `_Required` (400 d); **no analytics enabled**, no custom buckets/views |
| Sinks | only `_Default`/`_Required`; no exclusions beyond defaults |
| Log-based metrics | none |
| Custom metric descriptors (`custom.googleapis.com/*`) | none |
| Alert policies | none |
| Notification channels | **none** — a verified recipient is a hard prerequisite for Phase 11 (see Blockers) |
| Dashboards | none |
| Logging IAM | no explicit Logging/Monitoring grants; agent SA `service1-831@…` is project **Owner** (pre-existing); Composer service agent has `composer.serviceAgent` + `ServiceAgentV2Ext` |

## 4. The Sprint 4 missing-logs defect — preflight diagnosis

Verified facts for the acceptance window (2026-07-18 22:00 → 07-19 01:40 UTC):

- Project-wide sweep by `resource.type`: **only** BigQuery/GCS/IAM audit
  entries plus 2 Composer admin-audit entries. Zero `airflow-worker`,
  `airflow-scheduler`, `dag-processor`, or task-log entries exist anywhere,
  including the `_AllLogs` view. The Sprint 4 filters were **correct**; the
  logs genuinely never reached Cloud Logging.
- Ingestion itself works: a `gcloud logging write` roundtrip during Sprint 4
  succeeded and that entry is still the only non-audit log in the project.
- Not an obvious IAM gap: `atlas-composer-runtime` holds `composer.worker`
  (includes `logging.logEntries.create`); Composer service agents hold
  required roles; Logging API enabled; `_Default` sink filter is standard.
- Task logs were also absent from the environment bucket (Composer 3 default
  is Cloud Logging only), so Sprint 4 diagnosis fell back to the Airflow
  REST API — which worked and remains the documented fallback.

Remaining hypotheses require a live environment (Phase 15): environment
`dataRetentionConfig.taskLogsRetentionConfig.storageMode` (not set explicitly
in Sprint 4), or a Composer 3 log-routing fault in the tenant→customer
stream. Resolution plan: recreate `atlas-dev`, use the built-in
`airflow_monitoring` DAG (runs every ~5 min) as a log canary, verify entries
with documented filters within 15 minutes of creation, and treat
`storageMode` explicitly at create time. This diagnosis gates every
log-dependent Sprint 5 deliverable and is therefore step 1 of live acceptance.

## 5. Composer

| Item | Value |
|---|---|
| `atlas-dev` exists now | no (deleted post-Sprint 4 per ADR-010; bucket also removed) |
| Image availability | `composer-3-airflow-3.1.7-build.13` **still available** in us-central1 (verified via imageVersions API; 5 versions listed) |
| Recreate config | small / us-central1 / runtime SA `atlas-composer-runtime` / env vars per `manage_atlas_composer.sh` (unchanged interface) |
| Sprint 4 lifecycle evidence | created ~22:05 UTC, deleted ~01:35 UTC (~3.5 h) |

## 6. Security preflight

- No secrets found in the sampled Sprint 4 logs (there were almost no logs).
- `sanitize_error_message` exists and is regression-tested (Sprint 4 D4).
- Redaction gaps to close in Phase 2: the structured-logging contract must
  enforce sanitization centrally, not per call site.
- Linked BigQuery log dataset expands the log-read boundary to BigQuery IAM —
  will be documented; dataset kept read-only; no broad `logging.privateLogViewer`.
- Sink writer identity: service account auto-created per sink; needs only
  `logging.bucketWriter` on the destination bucket (same-project routing is
  automatic).
- CI stays credentialless; WIF identities unchanged; no new broad grants
  planned. IAM additions (if any) gated on `ATLAS_APPROVE_IAM`.

## 7. Cost preflight

| Item | Measurement / projection |
|---|---|
| Current log ingestion | ~0 (only audit logs; free allotment 50 GiB/mo far above need) |
| Projected Atlas log volume | MB/day scale at 50k-row batches — negligible; retention proposal: 30 d for `atlas-observability` bucket (matches `_Default`, justified by synthetic workload) |
| Custom metrics | ~15 descriptors, labels bounded to {environment, dag_id, task_id, component, status, check_name, severity}; projected < 200 time series total — far below chargeable tiers |
| BigQuery 7-day baseline | 2,696 jobs, 10.61 GB processed, 22.70 GB billed (min-billing inflation on many small jobs — the dominant Atlas cost signal) |
| Monitor DAG cadence | 30 min while Composer live (bounded windows; each evaluation scans MB) |
| Composer live-acceptance window | small env ≈ $0.75–1.00/h; target < 5 h; teardown gated on `ATLAS_APPROVE_TEARDOWN` |
| Permanent after teardown | log bucket/view/sink, linked dataset, metric descriptors, dashboards, alert policies, `atlas_ops` tables — all ~zero at rest |

## 8. Data baselines (from `atlas_ops`, live-queried)

| Signal | Baseline |
|---|---|
| Successful runs | 9 (avg duration **171 s**, all 50,000 rows loaded) |
| Failed runs | 7 (avg 76 s to failure) |
| Rejection rate | **1.79 %** avg (rollback smoke: 49,105 accepted + 895 rejected = 50,000) |
| Last success | 2026-07-19 01:21:56 UTC (`atlas-smoke-640cd786-local1784423774-run`) |
| Schedule | manual/smoke-triggered today; `@daily` when deployed unpaused |
| Deployment duration | ~10–15 min end-to-end (fetch→smoke) per Sprint 4 evidence |
| Schema signatures | 8 datasets; contracts in repo (`sql/`, dbt models) — manifest source for Phase 9 |

Initial thresholds derived from these (labeled operational, not SLOs):
freshness warn 26 h / fail 30 h (daily schedule + slack); volume warn ±20 % /
fail ±50 % vs trailing-window median; rejection warn > 5 % / fail > 10 %;
cost warn/fail vs 7-day trailing bytes-billed median.

## 9. Blockers and approvals

| Gate | State |
|---|---|
| `ATLAS_APPROVE_PR18_MERGE` | exercised — PR #18 merged, main verified |
| `ATLAS_APPROVE_PROVISION` / `ATLAS_APPROVE_IAM` | assumed per Sprint 4 precedent ("IAM approved at every stage"); mutations remain plan-first |
| `ATLAS_APPROVE_COMPOSER_CREATE` | required before Phase 15 recreation (cost above) |
| `ATLAS_APPROVE_ALERT_CHANNEL` + **recipient** | **RESOLVED** — owner supplied the alert email in-session; email notification channel created: `projects/example-gcp-project/notificationChannels/6567861337166986657` ("Atlas Primary Operator (email)", enabled, recipient category: repository owner / primary operator). The address itself is intentionally not committed to Git |
| `ATLAS_APPROVE_LIVE_DRILLS` / `ATLAS_APPROVE_TEARDOWN` | required at Phases 16 / 15.9 |

## 10. Implementation sequence

1. **Phase 1–2** — architecture doc + ADR-011; structured logging contract
   (`src/atlas/observability/logging.py`) with correlation hierarchy,
   redaction, truncation, and contract tests. Wire step runner, DAG
   callbacks, and deploy scripts to it.
2. **Phase 3–4** — migrations 004/005/006 (`task_events`, `quality_results`,
   `monitor_evaluations`) + `atlas.ops.task_events`, `atlas.ops.quality_results`;
   Airflow callback instrumentation; warehouse reconciliation persists results;
   unit tests for every event path.
3. **Phase 5** — `bootstrap_observability.sh` (--plan/--apply/--status):
   `atlas-observability` analytics log bucket (30 d), `atlas-runtime` view,
   Atlas sink filter, linked `atlas_logs` dataset; saved queries in
   `observability/queries/`.
4. **Phase 6–7** — metric descriptors + publisher (`atlas.observability.metrics`),
   cardinality budget; BigQuery job labels in Python paths; dbt job-label
   config verified against dbt-bigquery 1.11 docs (fallback: identity-based
   attribution); `bigquery_cost.sql`; ADR-012.
5. **Phase 8–9** — `atlas_observability_monitor` DAG (30-min, read-only,
   bounded windows, no-data semantics, drill overrides via
   `config/observability.yaml`); schema-drift monitor with fixture-based
   classification tests.
6. **Phase 10–12** — alert policy JSONs + `manage_atlas_alerts.sh`;
   notification channel wiring (blocked pending recipient); dashboard JSON +
   idempotent deploy.
7. **Phase 13–14** — runbook, alert catalog, on-call model; CI gates for all
   observability artifacts; deployment bundle extended with monitor DAG +
   observability modules + migrations.
8. **Phase 15–17 (live)** — recreate Composer (approval), deploy candidate,
   **resolve the missing-logs defect first**, healthy 50k batch (Drill A),
   then Drills B–G, incident report from Drill B, teardown (approval).
9. **Phase 18–20** — cost review, security review, validation report, README
   and catalog updates; final CI; merge; `atlas-sprint-5-complete`.

Static work (steps 1–7) proceeds immediately; cloud mutations stop at their
approval gates with exact plans.
