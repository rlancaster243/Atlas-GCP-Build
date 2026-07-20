# Atlas Sprint 8 Context Pack

Durable summary from the single Phase-0 repository scan. Purpose: enable targeted
reads for the rest of Sprint 8 without re-scanning. Last verified commit:
`3f986aa` (origin/main). Sprint 8 branch:
`cursor/atlas-sprint-8-reference-handoff-64a2`.

## Repository map (in-scope: ``)

```
src/atlas/            generator ingestion loader validation  (Sprint 1 data plane)
                      batch pipeline config                    (run context, settings)
                      logging observability ops                (telemetry, audit, cost)
                      failure_injection                        (Sprint 6, disabled by default)
                      governance/  registry catalog lineage impact
                                   schema_check retention security_policy  (Sprint 7)
dbt/atlas_dbt/        sources staging intermediate core marts + tests + meta.governance
dags/                 atlas_batch_pipeline, atlas_observability_monitor
scripts/              validate_ci.sh (canonical) + 40 others (deploy/rollback/obs/perf/...)
governance/           policy classifications retention consumers non_dbt_assets
                      schemas/ changes/ generated/(catalog.json/md, lineage.json)
observability/        alerts/ dashboards/ logging/ metrics/ performance/ queries/ schema/
config/               atlas.yaml anomaly_profile.yaml observability.yaml
                      failure_scenarios.yaml cost_controls.yaml
sql/migrations/       001..008 + checksums.lock
docs/                 61 md, adr/ (19), evidence-sprint4..7/
                      apps/ packages/ transform/dbt/
```

## Source-of-truth hierarchy (reuse, do not duplicate)

1. **Code + config** = ground truth for behavior.
2. **dbt `meta.governance`** = model ownership/grain/classification/contract.
3. **`governance/*.yml`** = non-dbt asset governance + policy vocab.
4. **ADRs (002–020)** = decisions and rationale.
5. **`validation-report-sprint{1..7}.md`** = evidence of claims (live vs static).
6. Sprint 8 reference package = a **curated map** that links to 1–5, never a copy.

## Canonical commands (verified)

```bash
export PYTHONPATH=src                                # atlas.* modules live under src/
bash scripts/validate_ci.sh --mode static          # 21 gates, credentialless
python -m atlas.governance.catalog check            # governance + drift
python -m atlas.governance.lineage                  # lineage graph
python -m atlas.governance.impact --asset fct_events
bash scripts/run_performance_suite.sh               # dry-run baseline ($0)
python -m atlas.observability.cost_guard estimate --sql-file <f> --project example-gcp-project --location US
```

Install for a clean clone: `pip install -r requirements.txt -r requirements-ci.txt`
(the CI file provides yamllint + shellcheck so `workflow_yaml`/`shell_static`
run instead of skipping). dbt: `bash scripts/setup_dbt.sh`. Airflow (optional
local): `airflow/requirements-airflow.txt` (apache-airflow==3.1.7).

## Key invariants to consolidate in Phase 4 (already true in code)

- Raw artifacts immutable & run-scoped; `batch_id` = data identity;
  `pipeline_run_id` = one execution; exact rerun idempotent.
- `fct_events` grain = one row per `event_id`; within-batch dup vs cross-batch
  replay distinguished (ADR-006 amend, Sprint 7 Phase 3).
- accepted + rejected reconciles to raw; quality failure blocks publication.
- Applied migrations immutable (`checksums.lock`); PR CI credentialless;
  releases immutable; smoke gates success; rollback checks schema compat;
  Composer ephemeral.
- Governance metadata single source of truth; owners+grain required; schema
  changes classified; breaking needs migration+impact; permanent evidence can't
  get transient retention; secrets never in evidence.

## Live vs static evidence (must stay separated)

- **Live-proven:** Sprints 1–6 pipeline/deploy/recovery (BigQuery, Composer,
  CI runs in validation reports); Sprint 7 dry-run perf baseline + $0 cost block.
- **Static/test-proven:** Sprint 7 governance/schema/lineage/deprecation/security
  gates (282 tests + offline gates).
- **Blocked (not executed):** Sprint 7 live IAM reduction, billed perf suite,
  live retention application.

## Public-extraction hotspots (Phase 14 input)

Personal email/name in ~35 files (alerts JSON notification channel, Sprint 4/5
WIF/IAM docs, `bootstrap_github_wif.sh`, setup guides). Private project id
`example-gcp-project`, bucket/SA/dataset names pervasive. No credentials,
keys, or tokens committed (Sprint 7/8 secret_scan clean). No absolute local
paths or conversation-context references in `docs/`.

## Sprint 8 governance rules for its own artifacts

- Reference docs carry a `reference-manifest.yml` entry with `last_verified_commit`.
- Every major claim in the evidence index maps to a path + type + live/static.
- Blocked work is labeled BLOCKED, never "complete".
- One ADR only if a real decision is made (ADR-021 reference/handoff contract).
- New gate reuses the `run_gate`/`in_group` framework; no YAML logic duplication.
