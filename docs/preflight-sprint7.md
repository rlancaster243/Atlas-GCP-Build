# Atlas Sprint 7 Preflight — Governance, Contracts, Schema Evolution, Security, Performance, Cost

Verified live against `origin/main` and Git tags on 2026-07-19, before any
Sprint 7 implementation. Repository truth overrides the master prompt; any
discrepancies are noted inline.

## 1. Git and release state

| Item | Value |
| --- | --- |
| Current branch | `cursor/atlas-sprint-7-governance-64a2` (created from `main`) |
| `origin/main` HEAD | `1c2cc158c034f2920b1b39ce28a7ff93f375f335` (Sprint 6 release-table row) |
| Sprint 6 merge commit | `48da9d226e0e942095c0623e5bd71d06f5e32e36` — **matches prompt** |
| `atlas-sprint-6-complete` | resolves to `48da9d2…` — **matches expected** |
| Tags 1–5 | `270e7d5`, `5135778`, `8aa1d7a`, `b609ac1`, `476e20a` (all present, unchanged) |
| Working tree | clean |
| Sprint 7 branches | none existed prior to this run |
| Open PRs | #6 (setup-dev-env, draft), #3 (greptile, draft), #2 (duckdb starter, open) — all stale/unrelated to Atlas sprints; not a valid base |
| Latest CI on main lineage | Sprint 6 run `29694739152` — atlas-ci **success** |

Conclusion: Sprint 6 is properly merged and tagged; Sprint 7 branches cleanly
from `main`. No unresolved Atlas branch should be used as a base.

## 2. Sprint 6 inheritance

- **Completion evidence:** `docs/validation-report-sprint6.md`,
  `game-day-results-sprint6.md`, incident reports INC-S6-001/002, cost/security
  reviews. Composer torn down (`composer environments list` = **0 items**),
  bucket removed.
- **`recovery_actions` state:** table live (migration 007, 20 columns); **1 row**
  — `rec-s6-quarantine-atlas20260719`, `QUARANTINE_BATCH`, SUCCESS/VERIFIED.
- **task_events timing provenance:** migration 008 applied
  (`timing_source`, `timing_confidence`).
- **Alert state:** 10 policies; `Atlas: data stale` and
  `Atlas: Composer environment unhealthy` **DISABLED** (correct post-teardown
  baseline — they assert on an absent Composer); other 8 ENABLED.
- **Outstanding limitations carried into Sprint 7:**
  - **Same-date reprocessing defect (INC-S6-001):** `generate_events` seeds
    deterministically from `processing_date`, so multiple batches for one date
    share identical `event_id`s. `int_event_classification` dedups `event_id`
    **globally** (`row_number() over (partition by event_id …)`), so a second
    same-date batch inflates `is_duplicate_extra` to the full batch size and the
    batch-scoped `assert_source_anomaly_profile` test fails. **Sprint 7 Phase 3
    must resolve this.**
  - **Overlapping runs (INC-S6-002):** deploy unpauses the DAG, letting a
    scheduled interval contend with the smoke run. Mitigation was manual DAG
    pause; a durable fix is a Sprint 7/8 candidate (orchestration, lower
    priority than the governance mission).

### Current duplicate / grain invariants (must preserve)

- `fct_events`: `materialized=incremental`, `incremental_strategy=merge`,
  `unique_key=event_id`, `partition_by=event_date (date)`,
  `cluster_by=[event_name, country_code]`, `on_schema_change=fail`. **Grain: one
  row per `event_id`** — global fact uniqueness enforced.
- `int_event_classification`: full-table rebuild; `is_duplicate_extra` =
  `row_number() over (partition by event_id order by ingested_at desc, …) > 1`.
- Anomaly profile expectation (`tests/assert_source_anomaly_profile.sql`, per
  batch): duplicate_extra=50, null_user=500, invalid_country=200,
  date_timestamp_mismatch=300, future_dated=150, backdated=300, late=0.

## 3. Contracts & governance (current state — the gap Sprint 7 fills)

| Artifact | State |
| --- | --- |
| dbt model contracts | Only `stg_events` has `config.contract.enforced: true` with `data_type`s. Other layers have descriptions + tests but no enforced contract. |
| dbt `meta` (owner/grain/classification/consumers/contract_version) | **absent** on all models |
| dbt exposures | **none** |
| Source declarations | `models/sources/sources.yml` |
| Model descriptions | present (grain stated informally in prose) |
| CODEOWNERS | **none** |
| Schema manifests / versioned baselines | **none** (only `observability/schema/expected-schemas.json` for ops tables) |
| Migration records | `sql/migrations/manifest.txt` (001–008; ledger `atlas_ops.schema_migrations`, checksum-guarded) |
| Retention config | **none declared** (datasets/buckets rely on GCP defaults) |
| Classification metadata | **none** |
| Governance source-of-truth | **none** — Sprint 7 Phase 1 creates it |

**Source-of-truth decision (ADR-016):** dbt `meta`/properties will be
authoritative for dbt models; a small `governance/` registry will cover non-dbt
assets (raw/ops tables, buckets, DAGs, dashboards, log resources). A generated
catalog consolidates both. No triple-maintained metadata.

## 4. Lineage inputs available

- dbt `manifest.json` (via `dbt parse`/`compile`) — authoritative model DAG +
  source→model edges. dbt venv present at `/tmp/dbt-venv` / `.venv-dbt`.
- Airflow DAG task graph (`dags/atlas_batch_pipeline.py`,
  `atlas_observability_monitor.py`).
- Migration manifest + `atlas_ops` audit-table dependencies.
- No graph DB / metadata service exists or will be built (repo artifacts only).

## 5. IAM inventory (from Sprint 6 live `get-iam-policy`, to re-verify in Phase 7)

| Principal | Roles | Notes |
| --- | --- | --- |
| `atlas-composer-runtime@…` | `composer.worker`, `bigquery.jobUser`, `bigquery.dataEditor`, `bigquery.resourceViewer` | Composer runtime |
| `atlas-github-integration@…` | `bigquery.jobUser`, `bigquery.dataEditor` | CI (isolated datasets) |
| `atlas-github-deployer@…` | `bigquery.jobUser`, `bigquery.dataEditor`, `composer.user`, `composer.environmentAndStorageObjectAdmin` | deploy |
| `service-…@cloudcomposer-accounts` | `composer.serviceAgent`, `composer.ServiceAgentV2Ext` | Google-managed |
| Log sink writer | Logging service agent (intra-project sink) | Sprint 5 |
| Human operator / Cursor dev credential | pre-existing broad project access (documented since Sprint 4) | used for recovery DELETEs |

No Owner/Editor/broad-admin on Atlas identities; keyless WIF for GitHub. Phase 7
builds the full matrix with observed-usage and a candidate reduction + negative
test (gated on `ATLAS_APPROVE_IAM`).

## 6. Security posture (to formalize in Phase 8)

Existing controls: `gate_secret_scan` in CI; `sanitize_error_message` for audit
fields; structured-log field allowlist + truncation; notification evidence
stores only the email (recipient is a real address — must not be committed in
new evidence). Sample data is synthetic (`generate_events`). Public-repo
extraction review is explicitly deferred to Sprint 8.

## 7. BigQuery baseline (live)

| Table | Rows |
| --- | --- |
| `atlas_raw.events` | 850,000 |
| `atlas_core.fct_events` | 392,845 |
| `atlas_marts.mart_daily_event_metrics` | 2,804 |
| `atlas_ops.pipeline_runs` | 25 |
| `atlas_ops.task_events` | 257 |
| `atlas_ops.recovery_actions` | 1 |

Datasets present: `atlas_core`, `atlas_dbt_staging`, `atlas_intermediate`,
`atlas_logs`, `atlas_marts`, `atlas_ops`, `atlas_quarantine`, `atlas_raw`,
`atlas_staging`. `fct_events` is partitioned+clustered; raw `events` is
partitioned by `event_date`, clustered by `event_name, country_code`. Job
labels already applied (Sprint 5 ADR-012) for cost attribution. This is a
50k-per-batch dataset — performance claims will be scoped honestly (no
production-scale extrapolation).

## 8. Cost baseline

- **Permanent footprint:** the 9 BigQuery datasets (small), the
  `atlas-observability` log bucket (30-day retention), metric descriptors, 10
  alert policies, 1 notification channel, dashboard, audit tables, release
  bundle bucket `atlas-deployments-…`.
- **Composer:** absent (ephemeral; only created if a control genuinely needs it).
- **Existing cost guards (Sprint 6):** `validate_backfill_window` (7-day),
  `require_full_refresh_approval`, `enforce_dry_run_ceiling`,
  `guarded_query_config` in `src/atlas/observability/cost_guards.py`.
- **Sprint 7 additions:** `config/cost_controls.yaml`, a CLI estimator
  (`cost_guard estimate`), a performance-suite byte ceiling, and a
  required-partition-filter check. Proposed hard ceiling for the whole live
  window: **`ATLAS_MAX_PERFORMANCE_TEST_BYTES` default 5 GB**, individual query
  dry-run ceiling 1 GB (both overridable by approval).

## 9. Existing CI gate framework (to extend, not replace)

`scripts/validate_ci.sh` uses `run_gate <name> <fn>` with static/integration
modes. Static gates: secret_scan, shell_syntax, shell_static, workflow_yaml,
sql_migrations, python_format, python_lint, python_types, python_tests,
config_validation, observability_config, failure_injection, dbt_static.
`sql_migrations` currently checks additive-only/non-empty but **not** applied
-migration checksum immutability against the ledger — Sprint 7 will add
checksum-drift detection. New gates will follow the same `run_gate` pattern;
PR CI stays credentialless.

## 10. Do-not-touch confirmation

Out-of-scope paths present and will not be modified without a documented,
`apps/**`, `packages/**`, `transform/dbt/**`.

## 11. Approval requirements for the gated phases

Static implementation (Phases 1–6, 8, 13, 14 fixtures, most docs) needs **no
approval**. The following live actions are gated and will stop with a recorded
blocked-gate if approval is absent:

| Action | Variable |
| --- | --- |
| BigQuery performance suite (bounded) | `ATLAS_APPROVE_PERFORMANCE_TESTS=true` + `ATLAS_MAX_PERFORMANCE_TEST_BYTES` |
| Live enforcement demos (cost block, etc.) | `ATLAS_APPROVE_LIVE_ACCEPTANCE=true` |
| IAM reduction + negative test | `ATLAS_APPROVE_IAM=true` |
| Retention/lifecycle mutation | `ATLAS_APPROVE_RETENTION_MUTATION=true` |
| Composer create (only if required) | `ATLAS_APPROVE_COMPOSER_CREATE=true` |
| Teardown | `ATLAS_APPROVE_TEARDOWN=true` |
| Breaking-schema demo (fixtures only) | `ATLAS_APPROVE_BREAKING_SCHEMA_DEMO=true` |
| Ordinary dev-resource mutation | `ATLAS_APPROVE_PROVISION=true` |

Preflight complete. No resources mutated.
