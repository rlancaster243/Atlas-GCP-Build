# Atlas Sprint 3 DAG Catalog

## `atlas_batch_pipeline`

| Property | Value |
|----------|-------|
| Schedule | `0 6 * * *` UTC |
| Start date | 2026-07-01 |
| Catchup | false |
| Max active runs | 1 |

### Trigger conf keys

| Key | Purpose |
|-----|---------|
| `processing_date` | Override logical processing date |
| `batch_id` | Override stable batch identifier |
| `upload_once` | Fail upload on try 1 for retry evidence |
| `dbt_test_failure` | Enable inject_failure singular test |

### Task IDs

`resolve_run_context`, `ensure_audit_resources`, `start_run_audit`,
`preflight_environment`, `generate_events`, `upload_events`, `load_bigquery_raw`,
`validate_raw_load`, `dbt_seed`, `dbt_source_freshness`, `dbt_build`,
`validate_warehouse`, `publish_success_marker`, `write_run_summary`
