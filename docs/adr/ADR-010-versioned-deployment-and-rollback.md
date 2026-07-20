# ADR-010: Versioned Deployment, Rollback, and Ephemeral Composer Evidence

## Status

Accepted — 2026-07-18 (owner decisions recorded verbatim; implementation lands in
Sprint 4)

## Context

Sprint 4 introduces the first automated GitHub-to-GCP delivery path for the Atlas
batch pipeline. Three owner decisions taken on 2026-07-18 constrain the design:

1. **Composer is ephemeral.** The managed Composer environment exists only to
   capture live deployment, smoke, and rollback evidence. It must not stay alive
   and compound cost ("that's a hard no"). Sprint 4 completion is claimed on
   durable evidence, not on a permanently running environment.
2. **Composer image is `composer-3-airflow-3.1.7-build.13`.** The originally
   pinned `build.12` was retired upstream; see the ADR-005 amendment.
3. **The repository is on the GitHub Free plan.** Required reviewers on GitHub
   Environments and full branch-protection rules are not enforceable on private
   Free-plan repositories. Deployment governance therefore uses the fallback
   controls described below, and documentation must not claim reviewer gates
   that the plan cannot enforce.

## Decision

### Immutable versioned releases

- Every deployment builds a deterministic bundle containing only runtime assets
  (DAGs, `src/atlas`, runtime scripts, `dbt/atlas_dbt`, config, approved SQL
  migrations, dependency manifests) plus a `release-manifest.json` carrying the
  git SHA, versions, file checksums, and schema-compatibility declarations.
- Bundles are stored create-only under
  `gs://<ATLAS_DEPLOYMENT_BUCKET>/atlas/releases/<git_sha>/`. An existing release
  path with a matching checksum is reused; a differing checksum fails the build.
  Nothing is ever overwritten.
- The mutable Composer runtime path (`data/current/`) is always a
  promoted copy of one immutable release. Rollback re-promotes a prior release;
  it never mutates or deletes historical bundles, moves tags, or rewrites git
  history.

### Rollback rules

- Runtime rollback is permitted only when the prior release's manifest declares
  compatibility with the currently applied schema version
  (`min_compatible_schema_version`).
- BigQuery migrations are additive by default and are never automatically
  reversed. A rollback that would require reversing a destructive migration is a
  manual operator decision.
- A rollback is only claimed successful after its own smoke batch reaches
  terminal `SUCCESS` and `atlas_ops.deployments` records `ROLLED_BACK`.

### Ephemeral Composer lifecycle (cost control)

- The Composer environment is created (gated by
  `ATLAS_APPROVE_COMPOSER_CREATE=true`) only when the delivery pipeline is ready
  for live acceptance, and is **deleted after the evidence bundle is captured**.
- The permanent record of the deployment is the durable evidence, not the
  environment: `atlas_ops.deployments` and `atlas_ops.pipeline_runs` rows,
  immutable release bundles in GCS, GitHub Actions run logs and artifacts, and
  `docs/validation-report-sprint4.md`.
- Re-verification at any later date follows the documented runbook: recreate the
  environment from the pinned image, promote the tagged immutable release, rerun
  the smoke batch, delete the environment.
- Estimated cost of the evidence-capture window (small Composer 3 environment,
  measured in hours, not months) is recorded in the validation report. Leaving
  the environment running (~$350–450/month) is explicitly rejected.

### Free-plan governance fallback

Because required environment reviewers and branch-protection API access are
unavailable on this plan:

- Deployment workflows trigger only via `workflow_dispatch` with an exact typed
  confirmation input, verify the target SHA is reachable from `origin/main`, and
  serialize under an `atlas-dev-deployment` concurrency group.
- No deployment triggers automatically from a pull request.
- The absence of enforced reviewer gates and branch protection is documented as
  an unresolved governance limitation in `docs/ci-cd-governance-sprint4.md`,
  together with the exact settings to enable if the repository is upgraded.

## Consequences

- Sprint 4's defensible claim is evidence-based: a validated change moved from an
  agent-created branch through independent CI and keyless GCP authentication to
  a real Composer deployment, smoke run, and tested rollback — all durable in
  audit tables, GCS, and workflow logs — even though the environment itself is
  deleted afterward.
- Anyone re-running acceptance must budget for environment creation time
  (typically ~25 minutes for Composer 3) plus the smoke matrix.
- If the GitHub plan is upgraded, governance should be revisited: enable branch
  protection on `main`, require the `atlas-ci-gate` check, and add required
  reviewers to the `atlas-dev` environment.
