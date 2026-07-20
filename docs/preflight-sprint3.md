# Sprint 3 Preflight Report

**Date:** 2026-07-14  
**Branch:** `cursor/atlas-sprint-3-airflow-orchestration-3660`  
**Repository:** `Atlas-GCP-Build/project-atlas`

## Version verification

| Component | Version | Notes |
|-----------|---------|-------|
| Airflow core | 3.1.7 | Composer-parity pin |
| Google provider | 20.0.0 | Composer-parity pin |
| Standard provider | 1.12.1 | Composer-parity pin |
| Composer image | `composer-3-airflow-3.1.7-build.12` | Verified 2026-07-14 |
| Local Python | 3.12.3 | Cloud Agent runtime |
| Composer Python | 3.11.8 | Documented parity gap |

Revisit ADR-005 if the Composer image is no longer available.

## Security scan

Tracked-secret checks (no credentials in git):

```bash
git grep -E '(BEGIN PRIVATE KEY|AIza[0-9A-Za-z\-_]{35}|service-account.*\.json)' -- ':!*.md' || true
grep -r 'credentials/' project-atlas --include='*.py' --include='*.yaml' || true
```

Results: no tracked private keys or service account JSON files. `.env`, `.gcp/`, and
`credentials/` remain gitignored.

## CLI inventory

| Script | Sprint 3 parameters |
|--------|---------------------|
| `generate_events.py` | `--processing-date`, `--batch-id`, `--pipeline-run-id`, `--seed` |
| `upload_events.py` | `--batch-id`, `--expected-checksum`, `--fail-once` |
| `load_events.py` | `--batch-id`, `--expected-row-count` |
| `validate_events.py` | `--batch-id`, `--processing-date`, `--mode` |
| `run_atlas_step.sh` | Dispatcher for all steps with structured context logs |
| `run_airflow_sprint3.sh` | Trigger and poll DAG runs |

## Reusable interfaces

- `atlas.batch.context` — batch and pipeline run identity
- `atlas.batch.manifest` — artifact checksums and idempotent reuse
- `atlas.ops.resources` — `atlas_ops` DDL
- `atlas.ops.audit` — MERGE upsert audit rows
- `atlas.loader.bigquery` — batch-scoped load idempotency
- `atlas.validation.checks` — run-scoped and batch-scoped validation

## Idempotency gaps addressed in Sprint 3

| Layer | Sprint 1/2 gap | Sprint 3 behavior |
|-------|----------------|-------------------|
| Generator | Wall-clock dates | Processing-date-based generation with manifest reuse |
| GCS | run_id paths only | `batch_id=` paths with checksum metadata |
| Raw load | pipeline_run_id skip | batch_id count evaluation (0/load, exact/skip, partial-fail, excess-fail) |
| dbt | run_id tests only | batch_id lineage + scoped reconciliation |
| Audit | None | `atlas_ops.pipeline_runs` one row per execution |

## Composer deployment contract

| Asset | Local path | Composer path |
|-------|------------|---------------|
| DAGs + parse helpers | `dags/` | `/home/airflow/gcs/dags/project_atlas/` |
| Scripts + dbt | `` | `/home/airflow/gcs/data/` |
| `ATLAS_ROOT` | repo `` | `/home/airflow/gcs/data/project-atlas` |
| `DBT_PROJECT_DIR` | `dbt/atlas_dbt/` | `/home/airflow/gcs/data/dbt/atlas_dbt` |

No DAG assumes `~/Atlas-GCP-Build/project-atlas`. Generated artifacts never write under Composer `dags/` or `plugins/`.
