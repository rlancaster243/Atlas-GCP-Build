# Atlas IAM & Least-Privilege Review (Sprint 7)

Live read-only inventory of `example-gcp-project` on 2026-07-19 via
`gcloud projects get-iam-policy` and per-SA `get-iam-policy`. No IAM mutation was
performed (see the blocked gate at the end — `ATLAS_APPROVE_IAM` is not set).

## Identity inventory

| Principal | Type | Purpose | Roles (project unless noted) | Assessment |
| --- | --- | --- | --- | --- |
| `atlas-composer-runtime@…` | SA | Composer/Airflow runtime | `composer.worker`, `bigquery.jobUser`, `bigquery.dataEditor`, `bigquery.resourceViewer` | Appropriate; writes all atlas_* datasets |
| `atlas-github-deployer@…` | SA (WIF) | CI/CD deploy + migrations | `bigquery.jobUser`, `bigquery.dataEditor`, `composer.user`, `composer.environmentAndStorageObjectAdmin` | Appropriate for deploy/migrate; WIF-scoped |
| `atlas-github-integration@…` | SA (WIF) | PR integration tests | `bigquery.jobUser`, `bigquery.dataEditor` | **Excess:** project-level `dataEditor` broader than its isolated CI datasets need |
| `service-911…@cloudcomposer-accounts` | Google-managed | Composer service agent | `composer.serviceAgent`, `composer.ServiceAgentV2Ext` | Google-managed; do not modify |
| `123456789012-compute@developer` | Google default SA | (unused by Atlas) | `roles/editor` | **Project hygiene finding:** default-SA Editor; not Atlas-created, out of Atlas scope to remove |
| `service1-831@…` | SA | bootstrap | `roles/owner` | Pre-existing bootstrap owner; not Atlas-created |
| `russell.lancaster243@gmail.com` | human | operator/owner | `roles/owner` | Human operator; expected |

### Keyless authentication (WIF)

Both GitHub SAs are bound only via `roles/iam.workloadIdentityUser` to:

```
principalSet://…/workloadIdentityPools/atlas-github-pool/
  attribute.repository_and_ref/YOUR_GITHUB_OWNER/YOUR_REPOSITORY@refs/heads/main
```

- **No service-account keys exist** (keyless).
- Trust is scoped to the **exact repo and `main` ref** — a fork or non-main ref
  cannot assume these identities. This trust condition must not be weakened.

## IAM evidence matrix

| principal | required_permissions | observed usage | excess | recommended_action | change_applied | neg_test | pos_test |
| --- | --- | --- | --- | --- | --- | --- | --- |
| composer-runtime | jobUser + dataEditor on atlas_* + composer.worker | pipeline runs, dbt builds | none material | keep | n/a | blocked | blocked |
| github-deployer | jobUser + dataEditor (migrations) + composer deploy | migrations, Composer deploy | slightly broad (dataEditor project) | keep (needs multi-dataset write) | n/a | blocked | blocked |
| **github-integration** | jobUser + dataEditor on **CI datasets only** | CI integration writes to isolated datasets | **project-level dataEditor** | **scope dataEditor to CI datasets (dataset-level grant); remove project-level** | **blocked (needs ATLAS_APPROVE_IAM)** | planned | planned |
| compute default SA | none (unused by Atlas) | none observed | `roles/editor` | out of Atlas scope; flag to project owner | n/a | n/a | n/a |

## Least-privilege rules confirmed

- No Owner/Editor on any **Atlas-created** SA. ✓
- No service-account keys (keyless WIF). ✓
- WIF trust conditions scoped to repo + `main`. ✓
- No broad Project IAM Admin on Atlas SAs. ✓
- No unnecessary cross-project permissions. ✓

## Justified reduction candidate (exact plan, gated)

**Target:** `atlas-github-integration` — replace project-level
`roles/bigquery.dataEditor` with dataset-level grants on the ephemeral CI
datasets only.

Mutation sequence (requires `ATLAS_APPROVE_IAM=true`):

1. Grant `bigquery.dataEditor` at the CI dataset scope (e.g. `atlas_ci_*`).
2. Remove the project-level `bigquery.dataEditor` binding for the SA.
3. **Positive test:** run the CI integration workflow → writes to `atlas_ci_*`
   succeed.
4. **Negative test:** as the same SA, attempt to write to `atlas_core`
   (a protected canonical dataset) → expect `PERMISSION_DENIED`.
5. Record both results; roll back the grant only if the positive workflow breaks.

The negative test uses a harmless denied write (no data loss). No
destructive/org-level action.

## Blocked completion gate

- **Gate:** live IAM reduction + positive/negative test.
- **Blocking approval:** `ATLAS_APPROVE_IAM=true` (not set in this environment).
- **Status:** static review complete; exact reduction plan produced above; no
  mutation performed. Per completion gate #20, this report documents the single
  justified reduction and the exact test plan; execution is pending approval.
  The gate is **not weakened** and no live proof is claimed.

## Honest limitations

- "Complete least privilege" is not claimed without permission-level usage
  telemetry; the review is role-scope-level with observed workload evidence.
- Default-compute-SA `roles/editor` and the bootstrap `roles/owner` are project
  hygiene items outside Atlas's created identities; flagged, not modified.
