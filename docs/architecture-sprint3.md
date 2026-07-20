# Project Atlas — Sprint 3 Architecture

## Overview

Sprint 3 wraps the Sprint 1 ingestion and Sprint 2 dbt warehouse in an Airflow 3.1.7
orchestration layer. Business logic remains in Python CLIs and dbt; Airflow owns
ordering, retries, publication, and finalization.

## Task graph

```text
resolve_run_context
  → ensure_audit_resources
  → start_run_audit
  → preflight_environment
  → generate_events
  → upload_to_gcs
  → load_bigquery_raw
  → validate_raw_load
  → dbt_seed
  → dbt_source_freshness
  → dbt_build
  → validate_warehouse
  → publish_success_marker
write_run_summary (all_done)
```

## Identity model

| Field | Scope | Example |
|-------|-------|---------|
| `batch_id` | Stable data batch | `atlas-20260715` |
| `pipeline_run_id` | One execution | `atlas-airflow-20260715-manual__...` |

## Deployment contract

| Asset | Composer path |
|-------|---------------|
| DAGs | `/home/airflow/gcs/dags/project_atlas/` |
| Scripts + dbt | `/home/airflow/gcs/data/` |

Set `ATLAS_ROOT=/home/airflow/gcs/data/project-atlas`.

## Retry policy

| Task | Retries |
|------|---------|
| upload, load | 2 (exponential backoff) |
| dbt freshness | 1 (scheduled mode) |
| validation, dbt build | 0 |

Historical backfill runs skip blocking freshness with a documented `SKIPPED` result.
