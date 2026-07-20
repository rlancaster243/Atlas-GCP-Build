# ADR-018: Identity and Access Boundaries

- Status: Accepted (Sprint 7)
- Date: 2026-07-19
- Deciders: cloud security reviewer, CI policy engineer, platform

## Context

Atlas uses four created service accounts plus Google-managed agents. Sprint 4
established keyless Workload Identity Federation; Sprint 7 formalizes the
identity boundaries and makes prohibited IAM patterns enforceable.

## Decision

### Identity boundaries

- **`atlas-composer-runtime`** — Airflow runtime. `composer.worker`,
  `bigquery.jobUser`, `bigquery.dataEditor` (atlas_* datasets),
  `bigquery.resourceViewer`.
- **`atlas-github-deployer`** — CI/CD deploy + migrations. `bigquery.jobUser`,
  `bigquery.dataEditor`, `composer.user`,
  `composer.environmentAndStorageObjectAdmin`. WIF-only.
- **`atlas-github-integration`** — PR integration tests. `bigquery.jobUser` +
  `bigquery.dataEditor` **scoped to CI datasets** (reduction candidate,
  ADR-018/§reduction). WIF-only.
- **Google-managed** Composer agents — not modified.

### Prohibited IAM patterns (enforced by `gate_security_policy`)

Managed Atlas IAM policy definitions in the repository must never grant:

- `roles/owner`, `roles/editor`, `roles/resourcemanager.projectIamAdmin`;
- service-account keys (keyless WIF only);
- weakened WIF trust conditions (must retain repo + ref scoping);
- unnecessary cross-project permissions.

### Change discipline

- No permission removal without a positive-use test proving valid workflows
  still succeed and a negative test proving the removed permission is denied.
- IAM mutations require `ATLAS_APPROVE_IAM=true`; missing approval yields a
  documented plan and a blocked gate, never a weakened control.

## Consequences

- The IAM posture is documented in an evidence matrix (`iam-review-sprint7.md`).
- A repository-level CI gate rejects prohibited roles in any managed policy
  definition, catching regressions before deployment.
- The one justified reduction (`atlas-github-integration` project→dataset
  `dataEditor`) is specified with positive/negative tests, pending approval.

## Honest limitations

- Least privilege is asserted at role scope with workload evidence, not with
  per-permission usage telemetry.
- Default-compute-SA `roles/editor` and bootstrap `roles/owner` are pre-existing
  project-level items outside Atlas's created identities; flagged, not changed.
