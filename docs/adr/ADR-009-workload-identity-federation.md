# ADR-009: Keyless GitHub-to-GCP Authentication via Workload Identity Federation

- **Status:** Accepted (Sprint 4)
- **Date:** 2026-07-18
- **Deciders:** Project owner + Sprint 4 delivery agent (IAM approved by owner at every stage)

## Context

Sprint 4 requires GitHub Actions to authenticate to GCP project
`example-gcp-project` for isolated integration testing and controlled
Composer deployment. Storing a Google service-account JSON key as a GitHub
secret is a long-lived, exfiltratable credential and is prohibited by the
Sprint 4 mission statement.

## Decision

Use GitHub's OIDC token issuer with Google Workload Identity Federation and
short-lived service-account impersonation. No service-account key is ever
created.

### Resources (created live by `scripts/bootstrap_github_wif.sh`)

| Resource | Value |
|---|---|
| Project | `example-gcp-project` (number `123456789012`) |
| WIF pool | `atlas-github-pool` (global) |
| WIF provider | `atlas-github-provider` (OIDC, issuer `https://token.actions.githubusercontent.com`) |
| Integration SA | `atlas-github-integration@example-gcp-project.iam.gserviceaccount.com` |
| Deployer SA | `atlas-github-deployer@example-gcp-project.iam.gserviceaccount.com` |
| Deployment bucket | `gs://atlas-deployments-example-gcp-project` (versioned, uniform access) |
| CI bucket | `gs://atlas-ci-example-gcp-project` (uniform access, 7-day object TTL) |

### Trust conditions

Two layers, both required:

1. **Provider attribute condition** — tokens are rejected at the pool boundary
   unless
   `assertion.repository_owner == 'YOUR_GITHUB_OWNER' && assertion.repository == 'YOUR_GITHUB_OWNER/YOUR_REPOSITORY'`.
   The owner check guards against repository transfer/rename attacks.
2. **Per-SA impersonation binding** — `roles/iam.workloadIdentityUser` is
   granted only to the principal set
   `attribute.repository_and_ref/YOUR_GITHUB_OWNER/YOUR_REPOSITORY@refs/heads/main`,
   using a custom mapped claim `repository_and_ref = assertion.repository + '@' + assertion.ref`.
   Pull-request runs (`refs/pull/...`) and any other refs cannot impersonate
   either service account, which enforces the "trusted workflow code only"
   rule from Phase 7: only workflows executing code already merged to `main`
   can obtain GCP credentials.

Mapped claims: `sub`, `repository`, `repository_owner`, `ref`,
`repository_and_ref`.

### Identity separation and least privilege

Two identities because integration testing and deployment have different
blast radii:

| Role | `atlas-github-integration` | `atlas-github-deployer` |
|---|---|---|
| `roles/bigquery.jobUser` (project) | yes | yes |
| `roles/bigquery.dataEditor` (project) | yes † | yes † |
| `roles/storage.admin` on CI bucket | yes | no |
| `roles/storage.admin` on deployment bucket | no | yes |
| `roles/composer.user` (project) | no | yes |
| `roles/composer.environmentAndStorageObjectAdmin` (project) | no | yes |

Neither identity has Owner, Editor, Project IAM Admin, organization roles, or
service-account-key administration. Neither can mint keys or escalate IAM.

† **Documented risk:** BigQuery offers no IAM primitive that allows
"create datasets matching `atlas_ci_*` only". `roles/bigquery.dataEditor` at
project scope is the minimum role that lets the integration identity create
its ephemeral `atlas_ci_<run_id>` datasets, and it also technically permits
writes to canonical datasets. Compensating controls: (a) only `main`-ref
workflows can impersonate the SA, so the code path is repository-controlled
and reviewed; (b) the integration script derives all dataset names from
`GITHUB_RUN_ID` and never references canonical dataset names in write paths;
(c) all integration activity is auditable in Cloud Logging under the SA
identity. A future hardening option is a dedicated CI project.

### GitHub workflow contract

Jobs that authenticate must set exactly:

```yaml
permissions:
  contents: read
  id-token: write
```

and use `google-github-actions/auth` (pinned to a full commit SHA) with the
committed provider resource name and SA email. These identifiers are not
secrets — possession of them grants nothing without a token that satisfies
the conditions above — so they live in version-controlled workflow files rather
than GitHub secrets, which also keeps pull-request CI credentialless.

## Consequences

- Pull-request CI remains credentialless by construction (PR refs cannot
  impersonate).
- Rotating trust requires editing IAM bindings, not rotating secrets.
- `bootstrap_github_wif.sh` is idempotent and plan-first
  (`ATLAS_APPROVE_IAM=true` required for mutation), so drift can be repaired
  by re-running it.
- The final end-to-end proof is a real GitHub Actions run exchanging an OIDC
  token; captured as Phase 7/19 evidence in the validation report.
