# Atlas CI/CD Runbook — Sprint 4

Operator commands for validation, deployment, rollback, and recovery. All
scripts live in `scripts/`; workflows in `.github/workflows/`.

## 1. Local / agent validation (no cloud credentials needed)

```bash
cd Atlas-GCP-Build
bash scripts/validate_ci.sh --mode static            # everything
bash scripts/validate_ci.sh --mode static --group python
bash scripts/validate_ci.sh --mode static --group airflow
bash scripts/validate_ci.sh --mode static --group dbt
bash scripts/validate_ci.sh --mode static --group security-shell
```

Machine-readable results: `logs/ci/validate-ci-results.json`.

## 2. Isolated GCP integration test

Requires ADC (locally) or WIF (`atlas-integration` workflow, main-ref only).

```bash
bash scripts/validate_gcp_integration.sh
# GitHub: Actions → atlas-integration → Run workflow (target SHA optional)
```

Creates `atlas_ci_<run>` datasets + `gs://atlas-ci-…/atlas-ci/<run>/`,
validates auth, determinism, idempotent loads, isolated dbt build, and
reconciliation, then deletes everything (verified). Orphan recovery:

```bash
bq ls --project_id example-gcp-project | grep atlas_ci_
bq rm -r -f -d example-gcp-project:<dataset>      # per leftover dataset
# GCS leftovers expire automatically after 7 days
```

## 3. Migrations

```bash
bash scripts/apply_atlas_migrations.sh --mode plan     # no mutation
bash scripts/apply_atlas_migrations.sh --mode status   # ledger dump
ATLAS_APPROVE_DEPLOY=true bash scripts/apply_atlas_migrations.sh --mode apply
```

Rules: append-only manifest (`sql/migrations/manifest.txt`), checksummed,
re-apply is a no-op, changed shipped files hard-fail, failures recorded as
FAILED in `atlas_ops.schema_migrations` and block promotion.

## 4. Release bundles

```bash
bash scripts/build_deployment_bundle.sh            # build + verify locally
bash scripts/build_deployment_bundle.sh --upload   # create-only GCS store
```

Stored under `gs://atlas-deployments-example-gcp-project/atlas/releases/<git_sha>/`.
Existing release with identical content → reuse; different content for the
same SHA → hard failure (immutability).

## 5. Ephemeral Composer environment (ADR-010: delete after evidence capture)

```bash
bash scripts/manage_atlas_composer.sh status
ATLAS_APPROVE_COMPOSER_CREATE=true ATLAS_APPROVE_IAM=true \
  bash scripts/manage_atlas_composer.sh create     # ~25-45 min total
bash scripts/manage_atlas_composer.sh delete       # ALWAYS after evidence
```

Image `composer-3-airflow-3.1.7-build.13`, size small, region `us-central1`,
runtime SA `atlas-composer-runtime@…`. dbt is installed as Composer PyPI
packages from `dbt/requirements-dbt.txt` pins.

## 6. Deployment

Preferred (post-merge): GitHub → Actions → `atlas-deploy` → Run workflow →
type `deploy-atlas-dev`. Script path (agent/operator with ADC):

```bash
ATLAS_APPROVE_DEPLOY=true bash scripts/deploy_atlas_release.sh \
  --git-sha <sha-reachable-from-main> [--leave-paused]
```

Stages and their failure recording (`atlas_ops.deployments.failure_stage`):
`fetch_release`, `schema_check`, `migrations`, `promote`, `dag_parse`,
`smoke_batch`, `smoke_validation`, `finalize`. A failed deployment records
`FAILED`, keeps the immutable bundle and logs, and prints the recovery
command. Re-running with the same `--git-sha` is safe.

## 7. Smoke validation (standalone)

```bash
bash scripts/validate_atlas_deployment.sh \
  --git-sha <sha> --deployment-id <id> \
  --batch-id atlas-smoke-<shortsha>-<run> \
  --pipeline-run-id atlas-smoke-<shortsha>-<run>-run \
  --processing-date YYYY-MM-DD
```

## 8. Rollback

GitHub: `atlas-rollback` → type `rollback-atlas-dev`. Script path:

```bash
ATLAS_APPROVE_ROLLBACK_TEST=true ATLAS_APPROVE_DEPLOY=true \
  bash scripts/rollback_atlas.sh [--target-sha <sha>]
```

Selects the newest prior `SUCCESS` deployment, verifies bundle checksums and
schema compatibility (a target requiring unapplied migrations is rejected),
re-promotes, runs a rollback smoke batch, records `ROLLED_BACK` /
`ROLLBACK_FAILED` with `previous_git_sha` linkage.

## 9. Common failures

| Symptom | Likely cause | Action |
|---|---|---|
| `atlas-ci-gate` red | any required job failed | open the failing job; every gate maps to a `validate_ci.sh` gate reproducible locally |
| WIF auth error in workflow | run not on `refs/heads/main` | deploy only merged SHAs; PRs can never authenticate (by design) |
| `fetch_release` failure | bundle missing for SHA | run `build_deployment_bundle.sh --upload` from that SHA (must be committed) |
| checksum mismatch on existing release | different content for same SHA | investigate immediately — never overwrite; the stored bundle is truth |
| `dag_parse` timeout | GCS sync delay or import error | `gcloud composer environments run atlas-dev --location us-central1 dags list-import-errors` |
| smoke `raw_batch_count` failure | partial load | check `atlas_ops.pipeline_runs` row and task logs; rerun deploy (idempotent loader skips complete batches) |
| migration CHECKSUM_MISMATCH | shipped SQL edited | revert the edit; add a new migration instead |
| leftover `atlas_ci_*` datasets | cleanup failed mid-run | see §2 orphan recovery |
| deployment stuck RUNNING | workflow died before finalize | re-run deploy with same SHA or finalize manually via `atlas.ops.deployments` |

## 10. Audit queries

```sql
-- deployments and rollbacks, newest first
SELECT deployment_id, deployment_type, status, git_sha, previous_git_sha,
       failure_stage, smoke_pipeline_run_id, completed_at
FROM `example-gcp-project.atlas_ops.deployments`
ORDER BY created_at DESC;

-- migration ledger
SELECT * FROM `example-gcp-project.atlas_ops.schema_migrations`
ORDER BY applied_at;

-- smoke run for a deployment
SELECT * FROM `example-gcp-project.atlas_ops.pipeline_runs`
WHERE pipeline_run_id = '<smoke_pipeline_run_id>';
```
