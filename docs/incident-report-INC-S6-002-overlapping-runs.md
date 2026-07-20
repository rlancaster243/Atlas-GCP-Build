# Atlas Incident Report — INC-S6-002: Overlapping Pipeline Runs During Deploy

Status: closed (contained). This report documents a real, unplanned
manifestation of the overlapping-run hazard catalogued as S6-AIR-004, observed
during the Sprint 6 deploy window. All timestamps are UTC on 2026-07-19.

## Summary

| Field | Value |
| --- | --- |
| Incident id | INC-S6-002 |
| Title | Scheduled catch-up run collided with deploy smoke run on shared dbt targets |
| Catalog scenario | S6-AIR-004 (overlapping runs) |
| Severity | MEDIUM (one run failed; no bad data published) |
| Affected component | `atlas_batch_pipeline` / `dbt_build` |
| Affected runs | `scheduled__2026-07-19T06:00` (FAILED) vs `smoke__atlas-dev-20260719T145242Z-b735823b` (SUCCESS) |
| Data impact | None published — failed run never produced a success marker |
| Containment | DAG paused so only explicit manual triggers ran for the rest of the window |

## Timeline (UTC, 2026-07-19)

| Time | Event | Evidence |
| --- | --- | --- |
| 14:52 | Deploy begins; assets promoted to Composer bucket | deploy log |
| ~14:53 | DAG promoted and unpaused to run smoke; Airflow also materialises the latest scheduled interval (`scheduled__2026-07-19T06:00`, catchup=False) | Airflow scheduler |
| 14:54 | Smoke run starts | deploy log (smoke run id) |
| 14:55–14:58 | Scheduled run progresses (`dbt_seed`, `dbt_source_freshness` SUCCESS) | `task_events` |
| 15:00:16 | Scheduled run `dbt_build` FAILED — contended with the concurrent smoke `dbt_build` on shared dbt target tables | `task_events` |
| 15:13:08 | Smoke run SUCCESS (12/12 smoke checks) | deploy log |
| 15:19 | DAG paused for the remainder of the game-day window | `dags pause` |

## Technical root cause

The DAG declares `max_active_runs=1` and `is_paused_upon_creation=True`, and the
deploy intentionally unpauses it only after promotion so the smoke run can
execute. At unpause, the scheduler evaluated the schedule (`0 6 * * *`,
`catchup=False`) and created the most-recent interval run for 06:00. That
scheduled run and the deploy's smoke run both executed `dbt build` against the
same shared dbt target datasets (`atlas_staging`/`atlas_intermediate`/
`atlas_core`/`atlas_marts`); concurrent builds of the same relations are not
safe, and the scheduled run's `dbt_build` failed.

`max_active_runs=1` limits *scheduled* concurrency but the smoke run is a
separately-triggered manual run and the scheduled run was created at the same
unpause moment, so the two overlapped briefly.

## Containment & prevention

- Containment: the DAG was paused immediately after the deploy window opened, so
  the rest of the game day used only explicit manual triggers with no scheduler
  contention. The failed scheduled run published nothing (no success marker).
- The failed scheduled run left a canonical batch (`atlas-20260719`) partially in
  raw/intermediate, which subsequently surfaced INC-S6-001; both were recovered.

### Recommended follow-ups (Sprint 7 candidates)

1. Keep the DAG paused during deploy/smoke and unpause only after smoke passes
   (or run smoke against an isolated smoke schema), so a scheduled interval can
   never contend with smoke.
2. Consider a deploy-time schedule freeze window, or a dbt build lock keyed on
   the target dataset, to make overlapping builds fail fast and cleanly rather
   than midway.
