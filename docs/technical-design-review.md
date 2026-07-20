# Project Atlas Technical Design Review — Sprint 1

## Objective

Deliver a cloneable, operable, and recoverable batch ingestion pipeline that
demonstrates senior data engineering competency without implementing future-phase
components prematurely.

## Architectural decisions

### 1. Nested project inside `de-project-1`

**Preferred because:** workspace-root MCP config must remain active for both Cursor
Desktop and Cloud Agents.

**Alternatives considered:** separate repository (cleaner ownership boundary) and
replacing the current repo (would discard DEOS scaffold).

**Tradeoffs:** two Python contexts and documentation overhead.

**Evolution:** v0.3 adds dbt models under `transform/dbt`; v0.4 adds Airflow DAGs
under `orchestration/airflow/dags` that invoke Atlas scripts.

### 2. Python modules plus shell bootstrap scripts

**Preferred because:** Cloud Shell-first execution with testable business logic.

**Alternatives considered:** shell-only pipeline and notebook-driven prototyping.

**Tradeoffs:** more files, but stronger testing and clearer ownership.

**Evolution:** Airflow BashOperator or PythonOperator can wrap the same scripts.

### 3. Run-scoped immutable GCS paths

**Preferred because:** Sprint 1 requires history never be overwritten.

**Alternatives considered:** date-only paths and object versioning alone.

**Tradeoffs:** longer object keys and more listing noise.

**Evolution:** backfill jobs can filter by `run_id` while retaining partition layout.

### 4. Staging-table load into partitioned target

**Preferred because:** explicit metadata enrichment and idempotent run replay.

**Alternatives considered:** direct append load and external tables.

**Tradeoffs:** one transient table per run.

**Evolution:** dbt staging model replaces transient table logic in v0.3.

### 5. Validation FAIL with acceptance anomaly detection

**Preferred because:** seeded bad rows should not produce a false green quality gate.

**Alternatives considered:** PASS when anomaly counts match profile and quarantine
invalid rows in Sprint 1.

**Tradeoffs:** operators must inspect acceptance checks, not only overall status.

**Evolution:** dbt tests and expectations reuse `config/anomaly_profile.yaml`.

## Security posture

- No credentials committed to git
- Cloud agent auth via Cursor secret `ATLAS_GCP_SERVICE_ACCOUNT_KEY`
- Bootstrap and live pipeline gated by `ATLAS_APPROVE_PROVISION=true`
- `.gcp/` ignored at repository root

## Testing strategy

- Unit tests for settings, generator, upload naming, and acceptance logic
- Integration test for local generate-only pipeline
- Acceptance tests for Sprint 1 repository layout and artifact generation
- Failure simulation script for missing file and bad schema cases

## Known limitations

- No dbt, Airflow, Terraform, CI/CD, or monitoring in Sprint 1
- Cloud agent MCP availability depends on Cursor secret injection and environment setup
- Live end-to-end execution requires sandbox permissions and explicit approval

## Validation report interpretation

| Signal | Expected Sprint 1 result |
| --- | --- |
| Overall validation status | `FAIL` |
| Row count / partition / schema checks | `PASS` after successful load |
| Duplicate/null/invalid/future/late checks | `FAIL` |
| Acceptance anomaly detection checks | Exact match to seeded profile |
| `future_timestamps` | `event_date > CURRENT_DATE()` — future calendar date, not clock time |

This is the intended professional posture: the pipeline detects bad data and
reports failure, while automated acceptance proves the detector works.
