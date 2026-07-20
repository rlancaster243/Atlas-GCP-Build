# Atlas Sprint 7 Context Pack

Durable summary from the single Phase-0 repository scan. Use this instead of
re-scanning; do targeted reads only. Paths are under ``.

## Repository map (in-scope)

- `src/atlas/` packages: `batch/` (identity, manifest), `config/` (settings),
  `failure_injection/` (registry, framework, cli), `generator/` (events),
  `ingestion/` (upload), `loader/` (bigquery), `logging/`, `observability/`
  (checks, cost, cost_guards, logging, metrics, monitor, schema_drift),
  `ops/` (audit, deployments, finalizer, migrations, preflight, quality_results,
  recovery_actions, resources, rollback_compatibility, task_events),
  `pipeline/` (orchestrator), `validation/` (checks, schema_versions, warehouse).
- `dags/` — `atlas_batch_pipeline.py`, `atlas_observability_monitor.py`,
  `atlas_orchestration/` (callbacks, commands, context, validation).
- `dbt/atlas_dbt/models/` — `sources/`, `staging/` (stg_events),
  `intermediate/` (int_event_classification, int_accepted_events,
  int_rejected_events), `core/` (dim_users, dim_countries, fct_events),
  `marts/` (mart_daily_event_metrics). Tests in `dbt/atlas_dbt/tests/`.
- `sql/` migrations 001–008 (`manifest.txt`); ledger `atlas_ops.schema_migrations`.
- `config/` — atlas.yaml, anomaly_profile.yaml, observability.yaml,
  failure_scenarios.yaml.
- `observability/` — alerts/, dashboards/, metrics/, queries/,
  schema/expected-schemas.json.
- `scripts/` — `validate_ci.sh` (gate framework), deploy/rollback,
  `manage_atlas_alerts.sh`, `manage_atlas_composer.sh`, step runner, etc.
- `docs/` + `docs/adr/` (ADR-002..015).

## Key mechanisms to reuse (do NOT rebuild)

- **CI gates:** `scripts/validate_ci.sh` → `run_gate <name> <fn>`; register in
  the `static`/`integration` blocks. `skip_gate <name> <reason>` for SKIPPED.
  Results JSON at `logs/ci/validate-ci-results.json`. Mirror in
  `.github/workflows/atlas-ci.yml` (credentialless PR CI).
- **Config validation pattern:** `gate_config_validation` /
  `gate_observability_config` load YAML and assert structure in an inline
  `python3 - <<'PY'`. New governance gates follow this.
- **Cost guards:** `src/atlas/observability/cost_guards.py` —
  `validate_backfill_window`, `require_full_refresh_approval`,
  `enforce_dry_run_ceiling`, `guarded_query_config`, `estimate_query_bytes`,
  `CostGuardViolation`, `emit_event`. Extend here; add `cost_guard estimate` CLI.
- **Schema modules:** `src/atlas/validation/schema_versions.py`
  (`SUPPORTED_SCHEMA_VERSIONS`, `CURRENT_SCHEMA_VERSION=2`, `detect/normalize`),
  `src/atlas/ops/rollback_compatibility.py` (`evaluate_rollback_compatibility`),
  `src/atlas/ops/migrations.py` (`Migration.breaking`, checksum ledger).
- **Audit:** `atlas.ops.*` (recovery_actions model is the template for durable,
  validated, idempotent BigQuery upserts with `emit_event`).
- **Settings/labeling:** `atlas.config.settings.load_settings`,
  `labeled_bigquery_client(project, component)`.

## Grain & duplicate facts (Phase 3 critical)

- `generate_events` seed = `default_seed_for_date(processing_date)` → identical
  event_ids for repeated dates.
- `int_event_classification`: `duplicate_rank = row_number() over (partition by
  event_id order by ingested_at desc, event_timestamp desc, source_file desc,
  raw_record_hash desc)`; `is_duplicate_extra = duplicate_rank > 1` (GLOBAL).
- `fct_events`: incremental merge, unique_key=event_id (global uniqueness).
- Fix must distinguish within-batch dup / cross-batch replay / exact rerun /
  conflicting dup / accepted canonical, preserve fct grain, keep 50 within-batch
  extras detectable, keep exact rerun idempotent. Prefer batch-scoped duplicate
  rank (option A) + replay classification (option B); confirm via ADR-017/an
  amendment. Use fixtures, never canonical destructive tests.

## Live baseline (2026-07-19)

Composer: 0 envs. Datasets: 9 (atlas_*). Rows: raw.events 850k,
core.fct_events 392,845, marts 2,804, ops.pipeline_runs 25, task_events 257,
recovery_actions 1 (VERIFIED). Alerts: 8 ENABLED, data-stale + composer-unhealthy
DISABLED (correct). GCP project `example-gcp-project`, location US/us-central1.

## Governance decisions locked in preflight

- ADR-016: dbt `meta` authoritative for models; `governance/` registry for
  non-dbt assets; generated consolidated catalog. No triple maintenance.
- Required asset fields: asset_id, asset_type, purpose, technical_owner,
  business_owner_or_role, grain, source, consumers, classification,
  retention_class, freshness_expectation, contract_version, lifecycle_status,
  repository_path, runbook, last_reviewed.
- Lifecycle: ACTIVE → DEPRECATED → REMOVAL_SCHEDULED → REMOVED.
- Classification: PUBLIC / INTERNAL / CONFIDENTIAL / RESTRICTED.
- Compatibility classes: COMPATIBLE / CONDITIONALLY_COMPATIBLE / BREAKING /
  PROHIBITED.

## New Sprint 7 CI gates (planned)

`gate_governance`, `gate_schema_compatibility`, `gate_lineage_impact`,
`gate_security_policy`, `gate_performance_cost`. All credentialless/static.
