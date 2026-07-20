# Project Atlas Sprint 2 Model Catalog

Validated run scope: `atlas-20260714T163527Z-19a0e4f6`

## Sources

| Name | Relation | Grain |
| --- | --- | --- |
| `atlas_raw.events` | `{project}.atlas_raw.events` | physical ingest row |

Freshness: warn after 24h, error after 48h on `ingested_at`.

## Seeds

| Model | Grain | Notes |
| --- | --- | --- |
| `valid_country_codes` | `country_code` | Ten active ISO-style codes from `config/anomaly_profile.yaml` |

## Staging

| Model | Materialization | Grain | Notes |
| --- | --- | --- | --- |
| `stg_events` | view | physical row | Normalized types, lineage, four temporal flags |

## Intermediate

| Model | Materialization | Grain | Notes |
| --- | --- | --- | --- |
| `int_event_classification` | table | physical row | Duplicate rank + terminal rejection reason |
| `int_accepted_events` | view | accepted canonical row | One accepted row per `event_id` |
| `int_rejected_events` | table (`atlas_quarantine`) | rejected physical row | All blocking defects |

## Core

| Model | Materialization | Grain | Notes |
| --- | --- | --- | --- |
| `dim_users` | table | `user_id` | First/last event timestamps from accepted events |
| `dim_countries` | table | `country_code` | Seed-backed reference |
| `fct_events` | incremental merge | `event_id` | Accepted events with warning flags retained |

## Marts

| Model | Materialization | Grain | Measures |
| --- | --- | --- | --- |
| `mart_daily_event_metrics` | table | `event_date, event_name, country_code, platform` | `event_count`, `distinct_user_count`, warning counts |

## Singular tests

| Test | Purpose |
| --- | --- |
| `assert_source_anomaly_profile` | Exact anomaly counts on validated run |
| `assert_raw_classification_reconciliation` | Raw physical rows = classification rows |
| `assert_fact_rejected_reconciliation` | Raw = accepted + rejected for validated run |
| `assert_mart_fact_reconciliation` | Mart totals = fact row count |

## Expected validated-run anomaly counts

| Measure | Expected |
| --- | ---: |
| duplicate_extra | 50 |
| null_user_id physical rows | 500 |
| invalid_country_code rejections | 200 |
| future_dated | 150 |
| event_time_late_arriving | 0 |
| backdated_event_date warnings | 300 |
| date/timestamp mismatch warnings | 300 |

Accepted canonical rows and rejected physical rows must sum to 50,000 raw rows.
