# Atlas Sprint 3 Validation Report

## Static validation (Cloud Agent)

| Gate | Result |
|------|--------|
| Unit + airflow tests (`pytest tests/`) | **47/47 PASS** |
| Shell syntax (`bash -n scripts/*.sh`) | PASS |
| DAG parse helpers (no network at import) | PASS |
| Composer path configuration tests | PASS |

## Live acceptance results (Cursor Cloud Agent — 2026-07-18)

Executed against GCP project `example-gcp-project` using the injected
`ATLAS_GCP_SERVICE_ACCOUNT_KEY` service account and a local Airflow 3.1.7
standalone. Root-cause fixes were required before any run progressed past the
first task (see "Diagnosed defects" below).

| # | Scenario | conf | Airflow run_id suffix | Audit status | Result |
|---|----------|------|-----------------------|--------------|--------|
| 1 | Retry success | `{processing_date:2026-07-18, batch_id:atlas-20260718, upload_once:true}` | `s1-20260718T170705Z` | `SUCCESS` | **PASS** — upload failed try 1, retried and succeeded, full dbt build + reconciliation green |
| 2 | Idempotent rerun | `{processing_date:2026-07-18, batch_id:atlas-20260718}` | `s2-idem-20260718T171453Z` | `SUCCESS` | **PASS** — GCS + raw load skipped (`already_loaded: true`); raw count stayed 50000 (not doubled) |
| 3 | dbt failure injection | `{processing_date:2026-07-01, batch_id:atlas-20260701, dbt_test_failure:true}` | `s3-dbtfail-20260718T171838Z` | `FAILED` | **PASS** — dbt build failed, no success marker, finalizer raised, audit `FAILED`; backfill freshness skipped |
| 4 | Historical recovery | `{processing_date:2026-07-01, batch_id:atlas-20260701}` | `s4b-recovery-20260718T180023Z` | `SUCCESS` | **PASS** (after temporal-semantics fix) — raw load skipped, dbt build 79/79, audit `SUCCESS` |
| 5 | Fresh historical batch | `{processing_date:2026-07-16, batch_id:atlas-20260716}` | `s5-freshhist-20260718T180320Z` | `SUCCESS` | **PASS** — native load wrote `processing_date` (50000 rows, 0 null); classified reproducibly |

Idempotency evidence (`atlas_raw.events`): batch `atlas-20260718` = **50000 rows,
1 distinct pipeline_run_id** after two runs.

Before/after for the temporal-semantics fix (same historical batch): scenario 4
was `FAILED` at `s4-recovery-...T172222Z`, then `SUCCESS` at
`s4b-recovery-...T180023Z` after the fix below.

## Diagnosed defects (fixed in this branch)

Every task initially failed. Root causes, all verified empirically against GCP:

1. **`run_atlas_step.sh` `${2:-{}}`** (primary) — bash parsed the default value as
   `{` plus a literal trailing `}`, appending a stray `}` to the JSON run context,
   so `json.loads` raised `Extra data` in **every** task. Replaced with an explicit
   default.
2. **`ops/audit.py` `_param_type(None)`** returned `STRING` for INT64 columns, so
   the audit MERGE failed (`Value of type STRING cannot be assigned … INT64`),
   blocking `start_run_audit`. Nullable numeric fields are now typed `INT64`.
3. **`ops/preflight.py`** used a broken `__import__(...).bigquery.Client` expression
   that always raised `AttributeError`, forcing preflight to `FAIL`. Replaced with a
   proper `from google.cloud import bigquery` import.
4. **`atlas_step_runner.py` / `airflow.env.example`** default GCS bucket name was
   missing `-events-`. Corrected.

## Resolved finding — historical backfills vs. anomaly profile

Originally, `assert_source_anomaly_profile` hard-asserted `future_dated=150`,
`event_time_late=0`, `backdated=300` — counts derived from `stg_events` flags
computed relative to wall-clock `ingested_at`. They were only reproducible for
same-day ingestion, so historical recovery (scenario 4) failed and, more
importantly, event classification itself was load-time dependent.

**Fix (option b + stopgap a), verified live:**
- **(b)** Added a nullable `processing_date` column to `atlas_raw.events`
  (persisted by the loader) and switched the three temporal flags to
  `COALESCE(processing_date, DATE(ingested_at))`. Backfills now classify
  identically to the original run. See ADR-003 "Sprint 3 refinement".
- **(a)** `assert_source_anomaly_profile` asserts the temporal counts only when
  every scoped row has `processing_date`, degrading gracefully for legacy rows.

Result: scenario 4 recovered `FAILED`→`SUCCESS`; a fresh historical batch
(`atlas-20260716`) loaded with native `processing_date` and passed 79/79.

## Live acceptance matrix (original Cloud Shell design)

Execute in `~/Atlas-GCP-Build/project-atlas` after merging Sprint 3:

### 1. Retry success (`upload_once`)

```bash
bash scripts/run_airflow_sprint3.sh \
  --processing-date $(date -u +%F) \
  --batch-id atlas-$(date -u +%Y%m%d) \
  --conf '{"upload_once": true}'
```

**Expected:** upload try 1 fails, try 2 succeeds, audit `SUCCESS`, run-summary reconciled.

### 2. Idempotent rerun (same batch, new pipeline run)

Re-trigger the same `--batch-id` with a new `--run-id`.

**Expected:** GCS skip, raw load skip, new audit row, zero fact/mart drift.

### 3. dbt failure (`dbt_test_failure`)

```bash
bash scripts/run_airflow_sprint3.sh \
  --processing-date 2026-07-01 \
  --batch-id atlas-20260701 \
  --conf '{"dbt_test_failure": true}'
```

**Expected:** dbt build fails, no success marker, audit `FAILED`.

### 4. Historical recovery

Re-run batch `atlas-20260701` without injection.

**Expected:** raw skip, successful backfill, freshness skipped, audit `SUCCESS`.

## Evidence (Cursor Cloud Agent — 2026-07-18, project `example-gcp-project`)

| Batch | pipeline_run_id | Status | Notes |
|-------|-----------------|--------|-------|
| current + upload_once | `atlas-airflow-20260718-manual__s1-20260718T170705Z` | `SUCCESS` | upload retried once then succeeded |
| idempotent rerun | `atlas-airflow-20260718-manual__s2-idem-20260718T171453Z` | `SUCCESS` | raw load skipped; raw stayed 50000 rows |
| historical dbt failure | `atlas-airflow-20260701-manual__s3-dbtfail-20260718T171838Z` | `FAILED` | dbt build failed as injected; finalizer raised |
| historical recovery (post-fix) | `atlas-airflow-20260701-manual__s4b-recovery-20260718T180023Z` | `SUCCESS` | raw skip OK; dbt build 79/79 after temporal-semantics fix |
| fresh historical batch | `atlas-airflow-20260716-manual__s5-freshhist-20260718T180320Z` | `SUCCESS` | native `processing_date` load; reproducible classification |
