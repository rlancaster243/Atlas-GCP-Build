# Project Atlas Sprint 1 Validation Report Template

Use this template after a live pipeline run.

## Run metadata

- Pipeline run id:
- Event date:
- Source GCS URI:
- Target table: `example-gcp-project.atlas_raw.events`
- Engineer:
- Environment: Cloud Shell / Cursor Desktop / Cursor Cloud Agent

## Core checks

| Check | Expected | Actual | Status |
| --- | --- | --- | --- |
| row_count | 50000 |  |  |
| partition_presence | >0 rows |  |  |
| schema_required_fields | true |  |  |
| duplicates | FAIL |  |  |
| null_user_ids | FAIL |  |  |
| invalid_country_codes | FAIL |  |  |
| future_timestamps | FAIL |  |  |
| late_arriving_events | FAIL |  |  |

## Acceptance checks

| Check | Expected | Actual | Status |
| --- | --- | --- | --- |
| acceptance_duplicate_detection | >= 50 |  |  |
| acceptance_null_user_detection | >= 500 |  |  |
| acceptance_invalid_country_detection | >= 200 |  |  |
| acceptance_future_timestamp_detection | >= 150 |  |  |
| acceptance_late_arrival_detection | >= 300 |  |  |

## Overall result

- Validation overall status:
- Acceptance anomaly detection status:
- Log file:

## Notes

Document any recovery actions taken for duplicate uploads, missing files, bad
schema, partial loads, or credential issues.
