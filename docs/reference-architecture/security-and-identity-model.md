# Security and Identity Model

**Status:** CURRENT · **Audience:** operator, reviewer, agent. Authoritative
detail: [iam-review-sprint7.md](../iam-review-sprint7.md),
[security-review-sprint7.md](../security-review-sprint7.md), ADR-009/018.

## Identities

| Identity | Type | Purpose | Auth | Notes |
| --- | --- | --- | --- | --- |
| Human operator | person | approvals, incident/release authority | Google account | approves `ATLAS_APPROVE_*` |
| Cursor development identity | agent SA (read-mostly) | local/dev inspection, MCP | short-lived key in Cursor secret | least-privilege |
| GitHub integration identity | SA | repository→GCP integration | **WIF (keyless)** | see excess note |
| GitHub deployer | SA | deploy releases | WIF (keyless) | scoped to deploy |
| Composer runtime | SA | Airflow execution | managed | ephemeral env |
| Log sink writer | SA | export logs to BigQuery | managed | write to `atlas_logs` |
| Monitoring/notification | managed | metrics, alerts, notify | managed | notification channel = operator email |

## Boundaries and rules (enforced)

- **Keyless WIF only** for GitHub→GCP; no service-account keys committed or
  created (INV-L2). Enforced by `gate_security_policy` (`scan_managed_iam`).
- No `roles/owner`, `roles/editor`, or broad Project IAM Admin. No weakening WIF
  trust conditions. ADR-018.
- Secrets never committed or written to evidence (INV-G8); enforced by
  `secret_scan` + `scan_data_exposure` + `validate_public_extraction.py`.

## Least-privilege status (honest)

Reviewed in Sprint 7. One justified reduction candidate remains: the
`atlas-github-integration` SA holds project-level `roles/bigquery.dataEditor`,
broader than required. A scoped reduction plus positive/negative test plan is
documented but **NOT executed** — it is BLOCKED on `ATLAS_APPROVE_IAM`
([unresolved-risks.md](unresolved-risks.md), RISK-01/02). We do **not** claim
complete least privilege without live permission-level evidence.

## Public-extraction risks

The operator email and private project id appear across configs and docs. These
are cataloged with dispositions in
`config/public_extraction_manifest.yml` + `scripts/validate_public_extraction.py`.
The repository is **not** published during Sprint 8.
