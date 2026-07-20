# Atlas CI/CD Governance — Sprint 4 (Phase 15)

## What GitHub plan limitations actually allow

The repository is **private on the GitHub Free plan**. Verified consequences
(API evidence, not assumption):

```text
$ gh api repos/YOUR_GITHUB_OWNER/YOUR_REPOSITORY/branches/main/protection
HTTP 403: Upgrade to GitHub Pro or make this repository public to enable this feature.
```

Unavailable and therefore **not claimed**:

- branch protection on `main` (required checks, PR-only merges, force-push
  blocks enforced server-side)
- GitHub Environments with required reviewers / self-review prevention
- tag protection rules

## Controls that ARE active (fallback model, ADR-010)

| Control | Mechanism | Where |
|---|---|---|
| Independent validation of every PR | `atlas-ci` workflow, path-scoped, credentialless | `.github/workflows/atlas-ci.yml` |
| Single stable gate name | `atlas-ci-gate` job aggregates all required jobs | same |
| Deployment cannot start from a PR | deploy/rollback are `workflow_dispatch` only | `atlas-deploy.yml`, `atlas-rollback.yml` |
| Typed confirmation | exact strings `deploy-atlas-dev` / `rollback-atlas-dev` | same |
| Only merged code can deploy | target SHA must satisfy `git merge-base --is-ancestor <sha> origin/main` | same |
| Only `main`-ref runs get GCP credentials | WIF impersonation bound to `repository_and_ref = …@refs/heads/main` (server-side, cannot be bypassed by a fork or PR) | ADR-009, GCP IAM |
| No overlapping deployments | `concurrency: group: atlas-dev-deployment`, `cancel-in-progress: false` | both deploy workflows |
| No stored cloud secrets | zero GitHub Actions secrets; OIDC only | repo settings |
| Supply-chain pinning | every third-party action pinned to a full commit SHA with the release tag in a comment | all workflows |
| Minimal token scopes | `permissions: contents: read` (+ `id-token: write` only where WIF is used) | all workflows |

The strongest governance boundary is deliberately placed **on the GCP side**
(WIF ref restriction), because GitHub-side branch protection cannot be
enforced on this plan. Even a direct push to a feature branch plus a manual
dispatch cannot obtain deployer credentials for non-main code.

## Commands to enable full protection after a plan upgrade

```bash
gh api -X PUT repos/YOUR_GITHUB_OWNER/YOUR_REPOSITORY/branches/main/protection \
  -F required_status_checks[strict]=true \
  -F "required_status_checks[contexts][]=atlas-ci-gate" \
  -F enforce_admins=true \
  -F required_pull_request_reviews[required_approving_review_count]=1 \
  -F restrictions=null \
  -F allow_force_pushes=false \
  -F allow_deletions=false
```

Also configure Environments `atlas-integration` and `atlas-dev` with required
reviewers and deployment-branch policy `main` (Settings → Environments; the
`environment: atlas-dev` reference already exists in the deploy workflows and
will pick the protections up automatically).

## Operating rules until then

1. Never merge a PR whose `atlas-ci-gate` is not green (human-enforced).
2. Never push directly to `main` (human-enforced; WIF limits the blast radius
   of a violation to code that still had to pass through `main`).
3. Deployments and rollbacks only via the dispatch workflows or the audited
   scripts they call; every attempt lands in `atlas_ops.deployments`.
4. Release tags (`atlas-sprint-N-complete`) are created once, never moved.
