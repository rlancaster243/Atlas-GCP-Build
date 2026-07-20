# Atlas Sprint 5 Validation Report — Observability, Alerting, Incident Readiness

All claims below are backed by live execution on 2026-07-19 in project
`example-gcp-project` (evidence artifacts in `docs/evidence-sprint5/`), by
GitHub CI runs, or by unit/acceptance tests in this repository. Anything not
proven is listed under "Unresolved limitations".

## 1. Git and PR evidence

| Item | Value |
| --- | --- |
| Sprint 4 closeout | PR #18 merged; `atlas-sprint-4-complete` → `4251e94` (release commit `b609ac1a…`) |
| Sprint 5 base (origin/main) | `45543b68e392dde722e7c84baca8252406c2053a` |
| Sprint 5 branch / PR | `cursor/atlas-sprint-5-observability-64a2` / PR #19 (merged 2026-07-19T12:28:04Z) |
| Sprint 5 release commit (main) | `476e20a2edcd9e6ae2e7aa2169d0f0c0fb13247c` |
| Release tag | `atlas-sprint-5-complete` (annotated `fd79562`) → `476e20a` |
| Candidate head at acceptance | `2109310b6abbb0112efeb43fa46e997ff29ed9db` |
| CI on candidate head | run `29676039069` — atlas-ci **success** (all gates) |
| Earlier iteration evidence | runs `29673933498` (ba16f3c, success), `29672095446` (8fe17dc, success); failures `29671974067`/`29671854476` were the secret-scan and mypy defects fixed in-branch |

## 2. Deployed releases during acceptance

| Release SHA | Deployment id | Result |
| --- | --- | --- |
| `8fe17dc` | `atlas-dev-20260719T042641Z-8fe17dcd` | SUCCESS (first Sprint 5 candidate; exposed smoke re-validation defect, fixed in `ba16f3c`) |
| `ba16f3c` | `atlas-dev-20260719T045055Z-ba16f3cd` | SUCCESS — 12/12 smoke checks (Drill A batch, 50 000 rows) |
| `2109310` | `atlas-dev-20260719T061802Z-2109310b` | SUCCESS — 12/12 smoke checks; carries the two acceptance fixes |

Composer environment: `atlas-dev`, `composer-3-airflow-3.1.7-build.13`,
us-central1, SMALL, runtime SA `atlas-composer-runtime@…`. Both DAGs
(`atlas_batch_pipeline`, `atlas_observability_monitor`) parse with zero
import errors.

Lifecycle (ephemeral policy, ADR-010): created 2026-07-19T03:44:08Z, deleted
2026-07-19T07:37:56Z (≈ 3.9 h). Teardown sequence: both DAGs paused →
environment-dependent alerts disabled (`Atlas: Composer environment
unhealthy`, `Atlas: data stale`) → drill series reset to PASS → environment
deleted → orphaned Composer bucket removed → verified no incident opened
after teardown (zero `ViolationOpen` events post-07:10Z). Permanent
observability resources (log bucket/sink/view, linked dataset, metric
descriptors, alert policies, channel, dashboard, audit tables) remain
valid.

## 3. Observability planes (ADR-011) — live evidence

### Plane 1 — Operational audit (BigQuery)

- Migrations `004_create_task_events_table`, `005_create_quality_results_table`,
  `006_create_monitor_evaluations_table`: APPLIED in the
  `atlas_ops.schema_migrations` ledger (checksums recorded).
- `task_events`: 74 rows captured for the three drill/smoke runs alone
  (`task-events-drills.json`) — STARTED/SUCCESS/FAILED/UPSTREAM_FAILED at
  (run, task, attempt, event) grain; retry-then-success distinguishable;
  repeated callbacks idempotent (unit-tested MERGE).
- `quality_results`: 20 rows for the drill runs (`quality-results-drills.json`)
  — `validate_warehouse` now persists real batch-scoped reconciliation
  results instead of printing PASS.
- `monitor_evaluations`: 91 rows during the window
  (`monitor-evaluations.json`), including drill-fixture rows explicitly
  tagged `source=atlas_drill_fixture`.

### Plane 2 — Logs (Cloud Logging)

- Dedicated bucket `atlas-observability` (us-central1, 30-day retention,
  analytics enabled), sink `atlas-observability-sink` (additive; `_Default`
  untouched), view `atlas-runtime`, linked read-only dataset `atlas_logs`
  (`log-routing-live.json`).
- Structured contract events flow live: 20 correlated entries for the Drill B
  run retrievable by one `jsonPayload.pipeline_run_id` filter
  (`drillb-correlated-logs.json`); the same entries are queryable through the
  linked dataset via SQL (15 rows returned in the verification query).
- **Platform defect (open):** Composer 3 `build.13` exports no Airflow
  component logs (worker/scheduler/task streams) to the customer project —
  reproduced from Sprint 4 and now root-cause-bounded: no `airflow-*` log
  names exist in any bucket including `_Default`; a manual `entries.write` to
  the identical logName/resource succeeds and routes correctly through both
  buckets; Composer's own task-log reader returns "Logs not found"; no
  org-policy/quota/IAM/exclusion cause exists in the project; a workload
  restart did not recover it. Mitigation shipped: `ATLAS_LOG_TO_CLOUD_LOGGING=true`
  makes every Atlas contract event write directly to logName `atlas-events`
  (never-raise, allowlist + sanitizer enforced), restoring queryable
  task-level telemetry. Raw Airflow stdout remains unavailable on this build.

### Plane 3 — Metrics and incidents (Cloud Monitoring)

- 15 custom descriptors under `custom.googleapis.com/atlas/...`; live series
  with real values for all pipeline/data/deployment metrics
  (`metric-timeseries-summary.json`). `check_status` has 22 series (11 checks
  × normal/drill) — inside the cardinality budget; labels validated at
  publish time (`validate_point`) and in CI.
- 10 alert policies live and enabled, all routed to the verified email
  channel `…/notificationChannels/6567861337166986657`
  (`notification-channel.json` — address not committed).
- Dashboard "Atlas Operations" (31 tiles) deployed and updated in place
  (`dashboard-live.json`).

## 4. Monitor DAG

`atlas_observability_monitor` runs every 30 minutes in Composer (unpaused for
the acceptance window), evaluates 11 checks with bounded windows, persists
evaluations, publishes metrics, and emits structured events. NO_DATA and
DISABLED states behave as designed (verified in evaluations evidence:
`cost_anomaly` NO_DATA before the IAM grant and with an insufficient
baseline).

## 5. Controlled drills (all executed live)

| Drill | Mechanism | Result | Incident evidence |
| --- | --- | --- | --- |
| A — normal success | 50 000-row smoke batches on `ba16f3c` and `2109310` + daily scheduled run 06:00 | complete task events, quality PASS, metrics live, dashboard current | n/a (healthy) |
| B — pipeline failure | deployed DAG run with `dbt_test_failure: true` | `dbt_build` FAILED → run FAILED → monitor FAIL → **incident 06:46:19** → email dispatch → clean rerun SUCCESS 06:58:00 → **auto-resolved 07:03:11** | `Atlas: pipeline failed`, violation `0.oaf4n04jvxx1`; full report in `incident-report-sprint5.md` |
| C — stale data | real freshness check, drill-only thresholds (1 s/2 s) via env override, `mode=drill` | freshness FAIL (age 196 s vs 2 s) | `Atlas: data stale` opened 07:04:54 (`0.oaf52a4f18hp`) |
| D — volume anomaly | fixture rows (10 000 vs 50 000 baseline) through the real check | FAIL, deviation 0.8 | `Atlas: critical volume deviation` opened 07:05:23 (`0.oaf52ofe3mrz`) |
| E — schema drift | doctored expected-schema manifest vs **live** `INFORMATION_SCHEMA` (no canonical mutation) | 2 BREAKING (type change, removed field) + 1 ALLOWED (allow-listed additive) — classification correct | `Atlas: breaking schema drift` opened 07:06:19 (`0.oaf53g1toeh7`) |
| F — cost anomaly | synthetic drill-mode FAIL point (`manage_atlas_alerts.sh test cost_anomaly`); zero real spend | policy fired | `Atlas: BigQuery cost anomaly` opened 07:06:49 (`0.oaf53uuk0td1`) |
| G — telemetry failure | fixture: terminal run with 9/13 terminal task events through the real check | FAIL, 4 missing | `Atlas: telemetry incomplete` opened 07:07:11 (`0.oaf545p85441`); plus the earlier **real** false-positive incident 06:05:51→06:33:00 that motivated the terminal-runs fix |
| Cleanup | PASS recovery points published to every drill series (`delete-test-resources`) | drill incidents auto-close after cessation | `incident-events.json` |

## 6. Defects found by live acceptance (converted into controls)

1. Smoke re-validation without `pipeline_run_id` crashed the new quality
   persistence → guard + fixed in `ba16f3c`.
2. `telemetry_completeness` false-positive on in-flight runs (opened a real
   incident at 06:05:51) → terminal-runs-only + regression test (`2109310`).
3. Composer log-export platform defect → direct-emission mitigation + tests
   (`2109310`), documented limitation.
4. Cost check 403 (`bigquery.jobs.listAll`) → `roles/bigquery.resourceViewer`
   grant + bootstrap script update.
5. Migration runner semicolon-in-comment and failed-migration-retry defects →
   fixed earlier in-branch with regression tests.

## 7. Notification evidence

- Channel: email, `projects/example-gcp-project/notificationChannels/6567861337166986657`,
  display name "Atlas Primary Operator (email)", enabled; recipient is the
  project owner's address supplied in-session (domain-only in evidence).
- Dispatch: 7 incident-open events and their notifications between 06:05 and
  07:07 (policy → channel binding shown in `alert-policies` live state).
- Limitation: Cloud Monitoring exposes no per-email delivery log; delivery
  confirmation rests on the channel configuration, the incident dispatch
  records, and the owner's mailbox.

## 8. CI evidence

The `observability_config` static gate validates thresholds, metric-catalog
cardinality, schema manifest, alert JSONs (placeholder channel, no secrets,
resolvable runbook anchors), dashboard JSON, and log-filter definitions.
Full static suite green locally and in GitHub CI on `2109310`
(run `29676039069`).

## 9. Completion-gate status (32 gates)

Gates 1–6, 8–32: **met** with the evidence above and in
`docs/evidence-sprint5/`.

Gate 7 ("Composer task logs are queryable through documented filters"):
**partially met** — Atlas task-level telemetry is queryable through the
documented `atlas-events` filters (structured contract events for every task
lifecycle transition), but raw Airflow component stdout is not exported by
Composer 3 `build.13` at all (platform defect, diagnosed and documented).
This is recorded honestly rather than claimed.

## 10. Unresolved limitations

- Composer 3 `build.13` component-log export defect (platform; mitigated for
  Atlas telemetry, unresolved for raw Airflow streams). Re-test on the next
  build upgrade.
- Email delivery latency not independently measurable (no delivery log for
  email channels).
- `task_events.FAILED` rows lack `completed_at`/`duration_ms` (Sprint 6
  cleanup).
- Thresholds in `observability.yaml` are initial operational thresholds
  calibrated on the synthetic 50 000-row workload — not production SLOs.
- Single-operator development ownership model; no real on-call rotation.
- Cost attribution covers labeled Python/dbt jobs; console-issued ad-hoc
  queries attribute only by identity.
