# Atlas Incident Report — Sprint 5 Controlled Pipeline-Failure Drill

Status: closed. This report documents the Sprint 5 Drill B incident: a
deliberately injected dbt test failure in the deployed `atlas_batch_pipeline`,
detected by the observability monitor, alerted through Cloud Monitoring, and
recovered by a clean rerun. Every timestamp below is UTC on 2026-07-19 and is
backed by artifacts in `docs/evidence-sprint5/`.

## Summary

| Field | Value |
| --- | --- |
| Incident title | Atlas pipeline failed — dbt build test failure (controlled drill) |
| Date | 2026-07-19 |
| Duration (failure → incident closed) | 06:41:47 → 07:03:11 (21 min 24 s) |
| Severity | CRITICAL (per `Atlas: pipeline failed` policy) |
| Affected component | `atlas_batch_pipeline` / `dbt_build` task |
| Detection source | `atlas_observability_monitor` → `custom.googleapis.com/atlas/monitor/check_status{check_name=latest_run_state}` |
| Alert policy | `Atlas: pipeline failed` (policy id `14992081806484518993`) |
| Violation id | `0.oaf4n04jvxx1` |
| Notification route | Cloud Monitoring email channel `projects/example-gcp-project/notificationChannels/6567861337166986657` ("Atlas Primary Operator (email)") |
| Operator | Primary operator (development ownership model, `on-call-model-sprint5.md`) |
| Data impact | None durable — failed batch never published a success marker; rerun replaced it idempotently |

## Timeline (UTC, 2026-07-19)

| Time | Event | Evidence |
| --- | --- | --- |
| 06:33:23 | Drill trigger: `atlas_batch_pipeline` run `drillb__pipeline-failure-20260719` with conf `dbt_test_failure: true` (batch `atlas-drillb-20260719`, run `atlas-drillb-20260719-run`) | Airflow API dag-run record |
| 06:33:54 | `atlas_ops.pipeline_runs` row created, status RUNNING | `pipeline_runs` |
| 06:39:00 | `dbt_build` task attempt 1 STARTED | `task-events-drills.json` |
| ~06:41 | `dbt_build` FAILED — injected dbt test failure (`inject_failure` var) | `task-events-drills.json` |
| 06:41:47 | Finalizer recorded pipeline run FAILED; `validate_warehouse` and `publish_success_marker` recorded UPSTREAM_FAILED | `pipeline_runs`, `task-events-drills.json` |
| 06:44:05 | Monitor evaluation: `latest_run_state` = FAIL / CRITICAL (run `drillb-monitor-eval-20260719`) | `monitor-evaluations.json` |
| 06:44:09 | `check_status{check_name=latest_run_state}` = 2 (FAIL) published | `metric-timeseries-summary.json` |
| 06:46:19 | Incident opened: `Atlas: pipeline failed`, violation `0.oaf4n04jvxx1`; notification dispatched to the email channel | `incident-events.json` |
| 06:48:56 | Recovery rerun `drillb__recovery-20260719` triggered — same `batch_id`, no injection (tests idempotent replacement) | Airflow API |
| 06:58:00 | Recovery run SUCCESS (`atlas-drillb-20260719-recovery-run`) | `pipeline_runs` |
| 07:01:17 | Monitor re-evaluation: `latest_run_state` = PASS | `monitor-evaluations.json` |
| 07:03:11 | Incident auto-resolved (`ViolationAutoResolve`) | `incident-events.json` |

Detection latency (pipeline FAILED recorded → incident open): **4 min 32 s**
(monitor was manually triggered for the drill; the scheduled 30-minute cadence
bounds worst-case detection at ~35 minutes).
Recovery latency (recovery SUCCESS → incident closed): **5 min 11 s**.

## Technical root cause

Observation: `dbt_build` executed `dbt build --vars {"validated_batch_id":
"atlas-drillb-20260719", "inject_failure": true}`. The `inject_failure` var
activates the controlled failing dbt test retained from Sprint 3 for exactly
this purpose. The dbt process exited non-zero; the step runner recorded a
FAILED task event and re-raised, Airflow marked the task failed (retries are
not configured for deliberate quality-gate failures), and downstream tasks
went to `upstream_failed`.

Inference: this is the intended behavior of the delivery controls — a failed
warehouse quality gate must stop publication. No defect in the pipeline
itself.

Contributing factor (real defect found and fixed during this drill window):
the first `telemetry_completeness` implementation evaluated the newest
`pipeline_runs` row even while it was still RUNNING, which opened a
false-positive `Atlas: telemetry incomplete` incident at 06:05:51 (violation
`0.oaf3pqgsimvt`, auto-resolved 06:33:00). Fixed in commit `2109310` (check
now only scores terminal runs) and regression-covered.

## Customer / data impact

None durable. Observation: the failed run's batch (`atlas-drillb-20260719`)
loaded raw rows but never passed `validate_warehouse` and never wrote a
success marker; marts never exposed the batch as validated. The recovery
rerun reused the same `batch_id`, replacing the batch idempotently
(`no_duplicate_load` semantics from Sprint 3/4 apply). `quality_results` for
the recovery run recorded all reconciliation checks PASS.

## Operator response (runbook execution)

Followed `observability-runbook-sprint5.md` → "Atlas: pipeline failed":

1. First query — latest run state and failed task from
   `atlas_ops.pipeline_runs` / `atlas_ops.task_events`: identified `dbt_build`
   attempt 1 FAILED. Worked as documented.
2. First log filter — `jsonPayload.pipeline_run_id="atlas-drillb-20260719-run"`
   on logName `atlas-events`: returned 20 correlated structured events
   covering every task lifecycle transition
   (`drillb-correlated-logs.json`). Worked as documented.
3. Containment — no action needed: failure propagation had already blocked
   publication.
4. Recovery — rerun without the injected defect per the runbook's "when a
   rerun is safe" rule (same batch id ⇒ idempotent replacement). Worked.
5. Verification — recovery SUCCESS in `pipeline_runs`, quality results PASS,
   monitor PASS, incident auto-closed.

## What worked

- Task-level audit (`task_events`) captured STARTED / FAILED /
  UPSTREAM_FAILED with correct grain, including the finalizer's backfill of
  never-scheduled tasks.
- Structured logs correlated the whole run by `pipeline_run_id` in one query,
  in both the `atlas-observability` bucket and the `atlas_logs` linked
  dataset.
- Monitor → metric → alert → email chain fired end to end with no manual
  glue.
- Idempotent rerun recovery behaved exactly as the Sprint 3 design promised.
- Incident auto-closed on recovery; no manual reset was needed.

## What failed / gaps observed

1. (Fixed) `telemetry_completeness` false positive on in-flight runs — fix in
   `2109310` with regression test
   (`test_observability_monitor.py`).
2. (Platform, open) Composer 3 `build.13` exports **no** Airflow component
   logs (worker/scheduler/task streams) to the customer project — reproduced
   from Sprint 4. Diagnosis evidence: zero `airflow-*` log names in any
   bucket including `_Default`; a manual `entries.write` to the identical
   logName/resource succeeds and routes correctly; Composer's own task-log
   reader reports "Logs not found"; environment restart did not recover it.
   Mitigation shipped in `2109310`: contract events are written directly to
   the Cloud Logging API (`atlas-events`) when
   `ATLAS_LOG_TO_CLOUD_LOGGING=true`, so Atlas telemetry no longer depends on
   the broken export path. Raw Airflow stdout remains unavailable and is
   documented as an unresolved platform limitation.
3. `task_events.FAILED` rows have NULL `completed_at`/`duration_ms` (the
   failure callback does not receive reliable timing). Cosmetic; noted as a
   Sprint 6 cleanup candidate.
4. Email delivery latency was not independently measurable (Cloud Monitoring
   does not expose per-notification delivery logs for email channels);
   delivery is evidenced by channel configuration + incident dispatch and by
   the recipient's mailbox.

## Corrective actions

| Action | Type | Status | Owner |
| --- | --- | --- | --- |
| Only score terminal runs in `telemetry_completeness` | code + regression test | done (`2109310`) | primary operator |
| Direct Cloud Logging emission for contract events | code + tests + env var on atlas-dev | done (`2109310`) | primary operator |
| Grant `roles/bigquery.resourceViewer` to runtime SA for the cost check (403 found live) | IAM + bootstrap script update | done | primary operator |
| Record Composer log-export defect as known platform limitation; re-test on next Composer build upgrade | documentation | done (this report; validation report) | primary operator |
| Populate `completed_at`/`duration_ms` on FAILED task events | code | deferred to Sprint 6 | primary operator |

## Speculation (explicitly labeled)

The Composer log-export failure is deterministic across two environments and
two days on `composer-3-airflow-3.1.7-build.13`, while documentation states
Gen 3 streams logs to Cloud Logging by default. It plausibly affects this
very new build (released 2026-07-07) more broadly; we cannot verify Google's
internal log-agent state from the customer project. This is speculation, not
observation.
