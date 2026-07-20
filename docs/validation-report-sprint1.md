# Project Atlas Sprint 1 Validation Report

## Run metadata

- Pipeline run id: `atlas-20260714T163527Z-19a0e4f6`
- Event date: `2026-07-14`
- Source GCS URI: `gs://atlas-raw-events-example-gcp-project/raw/event_date=2026-07-14/run_id=atlas-20260714T163527Z-19a0e4f6/events.jsonl`
- Target table: `example-gcp-project.atlas_raw.events`
- Engineer: the primary operator
- Environment: GCP Cloud Shell

## Core checks

| Check | Expected | Actual | Status |
| --- | --- | --- | --- |
| row_count | 50000 | 50000 | PASS |
| partition_presence | >0 rows | 49550 | PASS |
| schema_required_fields | true | true | PASS |
| distinct_event_ids | 49950 | 49950 | PASS |
| duplicate_rows | 50 | 50 | PASS |
| duplicates | 50 groups | 50 | FAIL |
| null_user_ids | 500 | 500 | FAIL |
| invalid_country_codes | 200 | 200 | FAIL |
| future_timestamps | 150 future-dated rows | 150 after validator fix | FAIL |
| late_arriving_events | 300 | 300 | FAIL |
| partition_reconciliation | primary + other = total | 49550 + 450 = 50000 | PASS |

## Acceptance checks

| Check | Expected | Actual | Status |
| --- | --- | --- | --- |
| acceptance_duplicate_detection | 50 | 50 | PASS |
| acceptance_null_user_detection | 500 | 500 | PASS |
| acceptance_invalid_country_detection | 200 | 200 | PASS |
| acceptance_future_timestamp_detection | 150 | 150 after validator fix | PASS |
| acceptance_late_arrival_detection | 300 | 300 | PASS |

## Partition reconciliation

```text
49,550 rows on primary event_date (2026-07-14)
+   300 late-arriving rows (event_date earlier than timestamp date)
+   150 future-dated rows (event_date > generation date)
= 50,000 total loaded rows
```

Note: late-arriving and future-dated rows are seeded on distinct indices in Sprint 1.

## Future timestamp semantics

Sprint 1 defines a future-dated anomaly as:

```sql
event_date > CURRENT_DATE()
```

This measures future **calendar dates**, not timestamps later than the validation clock.

## Overall result

- Validation overall status: `FAIL` (expected for seeded raw anomalies)
- Acceptance anomaly detection status: `PASS` after validator fix
- Log file: `logs/atlas-20260714T163527Z-19a0e4f6.jsonl`

## Notes

Initial live run exposed two issues that were corrected before archival:

1. JSONL included `ingested_at` before load-time enrichment.
2. Future timestamp validation used clock-time comparison and over-counted same-day rows.

Both were fixed on branch `cursor/project-atlas-sprint1-3660`.
