# Project Atlas Sprint 2 Validation Report

## Status

**PASS** — live validation completed in GCP Cloud Shell on 2026-07-14.

## Scope

- Validated Sprint 1 run id: `atlas-20260714T163527Z-19a0e4f6`
- Raw table: `example-gcp-project.atlas_raw.events`
- dbt project: `dbt/atlas_dbt`
- Engineer: the primary operator
- Environment: GCP Cloud Shell (`example-gcp-project`)

## Live gates (Cloud Shell)

| Gate | Expected | Actual | Status |
| --- | --- | --- | --- |
| `dbt debug` | connection OK | OAuth OK, location US | PASS |
| `dbt seed` | 10 country rows | 10 rows in `atlas_staging.valid_country_codes` | PASS |
| source freshness | warn/error thresholds | PASS | PASS |
| `dbt build --full-refresh` | success | 76/76 steps in 48.12s | PASS |
| singular tests | 4/4 | 4/4 | PASS |
| generic + unit tests | all pass | 63/63 | PASS |
| raw/classification reconciliation | 50,000 = 50,000 | PASS | PASS |
| accepted + rejected reconciliation | 50,000 total | PASS | PASS |
| mart/fact reconciliation | equal totals | PASS | PASS |
| anomaly profile (validated run) | exact counts | see below | PASS |

Validation JSON: `logs/validation-sprint2-20260714T194335Z.json`

## Anomaly counts (validated run)

| Measure | Expected | Actual | Status |
| --- | ---: | ---: | --- |
| duplicate_extra | 50 | 50 | PASS |
| null_user_id | 500 | 500 | PASS |
| invalid_country (physical) | 200 | 200 | PASS |
| future_dated | 150 | 150 | PASS |
| event_time_late_arriving | 0 | 0 | PASS |
| backdated_event_date | 300 | 300 | PASS |
| date_timestamp_mismatch | 300 | 300 | PASS |

## Relation inventory (full refresh build)

| Relation | Rows (approx.) | Materialization |
| --- | ---: | --- |
| `atlas_staging.stg_events` | 50,000 | view |
| `atlas_intermediate.int_event_classification` | 50,000 | table |
| `atlas_intermediate.int_accepted_events` | 49,106 | view |
| `atlas_quarantine.int_rejected_events` | 894 | table |
| `atlas_core.dim_users` | 38,900 | table |
| `atlas_core.fct_events` | 49,100 | incremental table |
| `atlas_marts.mart_daily_event_metrics` | 571 | table |

Accepted canonical rows plus rejected physical rows reconcile to 50,000 raw rows.

## Performance evidence (full refresh)

| Step | Duration | Notes |
| --- | ---: | --- |
| `int_event_classification` build | 2.92s | 50k rows, 12.1 MiB processed |
| `int_rejected_events` build | 2.07s | 894 rows, 14.0 MiB processed |
| `fct_events` build | 3.48s | 49.1k rows, 13.5 MiB processed |
| `mart_daily_event_metrics` build | 2.23s | 571 rows, 1.8 MiB processed |
| Total `dbt build` | 48.12s | 76 steps, 0 errors |

dbt artifacts preserved under `logs/dbt-artifacts/20260714T194137Z/`.

## Incremental idempotency (unchanged raw source)

**PASS** — validated in GCP Cloud Shell on 2026-07-14 after merge to `main` at `a137590`.

Command:

```bash
cd ~/Atlas-GCP-Build/project-atlas
export ATLAS_GCP_PROJECT_ID=example-gcp-project
bash scripts/validate_dbt_sprint2_incremental.sh
```

| Gate | Before | After | Status |
| --- | ---: | ---: | --- |
| `fct_events` row count | 49,106 | 49,106 | PASS |
| `mart_daily_event_metrics` event total | 49,106 | 49,106 | PASS |
| `int_rejected_events` row count | 894 | 894 | PASS |
| `dbt build` (no `--full-refresh`) | — | 76/76 in 60.61s | PASS |
| singular tests | — | 4/4 | PASS |

Validation JSON: `logs/validation-sprint2-incremental-20260714T201453Z.json`

## Notes

Sprint 1 terminology called 300 rows "late_arriving_events" using
`event_date < DATE(event_timestamp)`. Sprint 2 reclassifies those rows as backdated declared
dates. See [ADR-003](adr/ADR-003-corrected-temporal-semantics.md).

Singular anomaly test counts physical invalid-country rows (`NOT is_valid_country`), not
terminal `rejection_reason`, because null-user precedence suppresses some invalid-country
rejections while the physical defect remains.
