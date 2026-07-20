# Atlas Deployment Catalog — Sprint 4

Living record of Sprint 4 delivery artifacts and cloud resources. Durable
per-attempt records live in `atlas_ops.deployments` (query examples in the
runbook §10); this catalog documents the fixed resource inventory.

## Source-control artifacts

| Artifact | Value |
|---|---|
| Sprint 4 foundation PR | #14 (squash `21d54ed`) — Phases 0–3 |
| Gate-demonstration PR | #15 (closed unmerged by design) — Phase 16 |
| Delivery PR | #16 — Phases 5–15, 17–19 |
| Release tag (on completion) | `atlas-sprint-4-complete` |

## GCP resource inventory (created by Sprint 4)

| Resource | Name | Lifecycle |
|---|---|---|
| WIF pool | `atlas-github-pool` | permanent |
| WIF provider | `atlas-github-provider` (repo-restricted) | permanent |
| Service account | `atlas-github-integration@…` | permanent |
| Service account | `atlas-github-deployer@…` | permanent |
| Service account | `atlas-composer-runtime@…` | permanent (no cost when Composer absent) |
| Bucket | `gs://atlas-deployments-example-gcp-project` (versioned) | permanent — immutable releases |
| Bucket | `gs://atlas-ci-example-gcp-project` (7-day TTL) | permanent, self-cleaning |
| BigQuery table | `atlas_ops.schema_migrations` | permanent |
| BigQuery table | `atlas_ops.deployments` | permanent |
| Composer env | `atlas-dev` (us-central1, `composer-3-airflow-3.1.7-build.13`, small) | **ephemeral** — created for evidence capture, deleted afterwards (ADR-010) |
| Ephemeral datasets | `atlas_ci_<run>_…` | per integration run, auto-deleted |

Sprint 5 additions (details: `validation-report-sprint5.md`):

| Resource | Name | Lifecycle |
|---|---|---|
| BigQuery tables | `atlas_ops.task_events`, `atlas_ops.quality_results`, `atlas_ops.monitor_evaluations` | permanent (migrations 004–006) |
| Log bucket | `atlas-observability` (us-central1, 30-day retention, analytics) | permanent |
| Log sink / view | `atlas-observability-sink` / `atlas-runtime` | permanent |
| Linked dataset | `atlas_logs` (read-only) | permanent |
| Metric descriptors | 15 × `custom.googleapis.com/atlas/...` | permanent |
| Alert policies | 10 × `Atlas: …` (environment-dependent ones disabled between acceptance windows) | permanent |
| Notification channel | `Atlas Primary Operator (email)` | permanent |
| Dashboard | `Atlas Operations` (31 tiles) | permanent |

## Release bundle registry

Immutable bundles: `gs://atlas-deployments-example-gcp-project/atlas/releases/<git_sha>/`
(`atlas-bundle.tar.gz`, `.sha256`, `release-manifest.json`). List releases:

```bash
gcloud storage ls gs://atlas-deployments-example-gcp-project/atlas/releases/
```

Bundle contents and manifest fields: `architecture-sprint4.md`. Live
deployment evidence for Sprint 4 acceptance (bundle URIs, checksums,
deployment ids, smoke run ids, rollback linkage):
`validation-report-sprint4.md`.

## Version pins in force

| Component | Version | Where pinned |
|---|---|---|
| Python (CI/runtime) | 3.12 | workflows `PYTHON_VERSION` |
| apache-airflow | 3.1.7 (+ official constraints) | `airflow/requirements-airflow.txt` |
| providers google / standard | 20.0.0 / 1.12.1 | same |
| dbt-core / dbt-bigquery | 1.11.12 / 1.11.3 | `dbt/requirements-dbt.txt` |
| dbt-utils | pinned via `dbt/atlas_dbt/package-lock.yml` | dbt deps |
| Composer image | `composer-3-airflow-3.1.7-build.13` | `manage_atlas_composer.sh`, ADR-005 |
| CI toolchain (ruff, mypy, yamllint, shellcheck-py, pytest) | see file | `requirements-ci.txt` |
| actions/checkout | v5 `93cb6efe…` | all workflows |
| actions/setup-python | v6 `ece7cb06…` | all workflows |
| actions/upload-artifact | v4 `ea165f8d…` | all workflows |
| google-github-actions/auth | v3.0.0 `7c6bc770…` | WIF workflows |
| google-github-actions/setup-gcloud | v3.0.1 `aa5489c8…` | WIF workflows |

Action SHAs were resolved with `gh api repos/<owner>/<repo>/git/ref/tags/<tag>`
on 2026-07-18 and are updated deliberately, never by floating tags.
