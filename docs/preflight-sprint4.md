# Sprint 4 Preflight Report — CI/CD, Secure GCP Delivery, Composer, Rollback

Compiled 2026-07-18 (updated as delivery progressed). All facts below were
verified against the live repository and GCP project, not assumed.

## Repository

| Item | Value |
|---|---|
| Repository | `YOUR_GITHUB_OWNER/YOUR_REPOSITORY` (private) |
| Baseline main SHA (Sprint 3) | `8aa1d7a1849d4226e30b367ae490dcf1df936f9a` — verified |
| Sprint tags | `atlas-sprint-1-complete`, `atlas-sprint-2-complete`, `atlas-sprint-3-complete` (→ `8aa1d7a`, added during Sprint 4 hygiene) |
| Sprint 4 PRs | #14 (Phases 0–3, merged as squash `21d54ed`), #15 (Phase 16 gate demos, closed by design), #16 (delivery continuation, this branch) |
| Pre-existing workflows | none for Atlas before Sprint 4; `atlas-ci.yml` added in PR #14 |
| Branch protection | **not readable/writable** — `gh api .../branches/main/protection` returns 403 on the current plan |
| GitHub plan | Free. Required reviewers on Environments and branch protection API are unavailable for private repos → governance fallback documented in ADR-010 and `ci-cd-governance-sprint4.md` |

## Validation toolchain (verified versions)

| Tool | Version |
|---|---|
| Python | 3.12.3 |
| uv | 0.11.29 |
| dbt-core / dbt-bigquery | 1.11.12 / 1.11.3 (pinned; 1.12 deliberately not adopted) |
| Apache Airflow | 3.1.7 + providers google 20.0.0, standard 1.12.1 |
| gcloud SDK | 576.0.0 (bq 2.1.34) |
| ruff / mypy / yamllint / shellcheck-py / pytest | pinned in `requirements-ci.txt` |

## GCP state

| Item | Value |
|---|---|
| Project | `example-gcp-project` (number `123456789012`) |
| Agent identity | `service1-831@example-gcp-project.iam.gserviceaccount.com` (project Owner — can create IAM/WIF/Composer; used only from the Cursor environment) |
| BigQuery datasets | `atlas_raw`, `atlas_{staging,intermediate,core,marts,quarantine}`, `atlas_ops` — location US |
| Buckets (pre-Sprint 4) | `atlas-raw-events-example-gcp-project` (no uniform bucket-level access — cannot carry IAM conditions) |
| Buckets (created Sprint 4) | `atlas-deployments-…` (versioned, uniform), `atlas-ci-…` (uniform, 7-day TTL) |
| Composer environments | none before Sprint 4; `composer-3-airflow-3.1.7-build.12` (ADR-005 target) no longer offered — owner approved `build.13` |
| WIF pools before Sprint 4 | none |

## Security preflight

- Tracked-file credential scan: clean (gate `secret_scan` in `validate_ci.sh`).
- Untracked scan: agent ADC material lives outside the repo (`/tmp`); nothing
  under `` matches key patterns.
- No long-lived GitHub Actions secrets exist; PR CI is credentialless and the
  WIF design (ADR-009) keeps it that way.
- Workflow permissions: all Atlas workflows declare least privilege
  (`contents: read`, plus `id-token: write` only for trusted WIF jobs).

## Cost review

- Composer 3 small: ≈ USD 0.35–0.50/hour while running (~USD 300/month if left
  alive). Owner decision: **hard no** on persistent environments — create for
  evidence capture, then delete (`manage_atlas_composer.sh delete`, ADR-010).
- Integration tests: ephemeral `atlas_ci_<run>` datasets + CI bucket objects
  (auto-TTL 7 days); per-run BigQuery cost is cents (50k-row batches).
- Deployment bundles: single-digit MB per release in GCS — negligible.
- Scale-to-zero: everything except retained BigQuery datasets and GCS bundles.

## Approval variables (owner grants on record)

| Variable | State |
|---|---|
| `ATLAS_APPROVE_PROVISION` | granted ("Build is approved") |
| `ATLAS_APPROVE_IAM` | granted ("IAM is approved at every stage") |
| `ATLAS_APPROVE_COMPOSER_CREATE` | granted for ephemeral evidence capture only |
| `ATLAS_APPROVE_DEPLOY` | granted |
| `ATLAS_APPROVE_ROLLBACK_TEST` | granted (rollback is a required completion gate) |

## Code interfaces (as found at Sprint 3 baseline)

- CI/test entry points: fragmented (`test_airflow_sprint3.sh` suppressed
  failures with `|| true`; `run_airflow_sprint3.sh` did not poll;
  `validate_warehouse` was a hardcoded PASS) — all fixed in Phase 1 with
  regression tests.
- No deploy scripts, no migration ledger, no deployment audit — built in
  Phases 8–11.
- dbt targets: `atlas*` datasets via `ATLAS_DBT_DATASET`; raw via
  `ATLAS_BQ_DATASET` (env override added to `settings.py` in Phase 7 so
  isolation requires no parallel code path).
- Composer path mapping (ADR-005, implemented Phase 12): DAGs →
  `<composer-bucket>/dags/project_atlas/`, runtime →
  `<composer-bucket>/data/current/`, immutable releases →
  `gs://atlas-deployments-…/atlas/releases/<git_sha>/`.
- Rollback limitation: BigQuery schema migrations are additive-only and never
  auto-reversed; runtime rollback requires manifest schema compatibility
  (ADR-010).
