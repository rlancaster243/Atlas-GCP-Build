# Atlas Sprint 6 Security Review

Scope: the resilience additions of Sprint 6 — the controlled fault-injection
framework, the recovery-action audit, cost guards, schema-version handling, and
rollback compatibility. Reviewed live on 2026-07-19 against project
`example-gcp-project`.

## Fault injection is safe by construction

The most security-sensitive addition is a framework that deliberately breaks
things. It is fenced by a layered safety contract (ADR-013,
`src/atlas/failure_injection/`), verified live and in CI:

| Control | Evidence |
| --- | --- |
| Disabled by default | `cli run` REFUSED without `ATLAS_APPROVE_FAILURE_INJECTION=true` (live) |
| Explicit scenario required | CLI errors if `--scenario` absent ("fault injection never runs implicitly") |
| No implicit environment | CLI errors if `--environment` absent for `run`/`cleanup`/`status` |
| Refuses scheduled/canonical/production contexts | `authorize_injection` rejects scheduled execution, canonical batch ids, and non-dev environments (unit-tested) |
| Bounded by duration/cost | each scenario declares `maximum_duration_minutes`/`maximum_cost_usd`; `enforce_deadline` bounds the window |
| Never an unattended destruction engine | `run` only authorizes and prints operator steps; it does not mutate cloud resources itself (CLI docstring + code path) |
| Not hardcodable in production paths | `gate_failure_injection` CI gate proves injection cannot be silently enabled in production code |
| Catalog integrity | `cli validate` = VALID; every scenario carries required fields, allowed categories/risk/mode, controlled recovery actions |

## Recovery audit integrity

- `atlas_ops.recovery_actions` records who/what/when for every recovery; `SUCCESS`
  is refused unless `verification_status=VERIFIED` (`_validate`, ADR-014), so a
  recovery cannot be marked done without evidence.
- `error_summary` is passed through the audited `sanitize_error_message`
  (strips bearer tokens/key material/long opaque strings) — no secret leakage
  into the audit table.
- Upserts are idempotent by `recovery_id`; re-running a recovery cannot fork the
  audit history.

## Cost guards as a safety control

Cost guards are also a denial-of-wallet safeguard: `validate_backfill_window`,
`require_full_refresh_approval`, `enforce_dry_run_ceiling`, and
`guarded_query_config` block expensive operations unless an explicit approval
variable is set, and emit `cost_guard_blocked` telemetry when they do. This
prevents a mistyped date or an accidental full refresh from becoming a large,
silent scan.

## Schema-version handling

`atlas.validation.schema_versions` rejects unknown schema versions and unknown
fields (no silent coercion of untrusted payloads) and backfills explicit nulls
for older versions — preventing malformed/ambiguous input from being accepted as
valid (ADR-015).

## IAM evidence (live `gcloud projects get-iam-policy`, 2026-07-19)

No IAM changes were made in Sprint 6. Atlas identities retain exactly their
Sprint 5 roles:

| Principal | Roles | Notes |
| --- | --- | --- |
| `atlas-composer-runtime@…` | `composer.worker`, `bigquery.jobUser`, `bigquery.dataEditor`, `bigquery.resourceViewer` | runtime identity; unchanged |
| `atlas-github-integration@…` | `bigquery.jobUser`, `bigquery.dataEditor` | isolated CI datasets; unchanged |
| `atlas-github-deployer@…` | `bigquery.jobUser`, `bigquery.dataEditor`, `composer.user`, `composer.environmentAndStorageObjectAdmin` | deploy identity; unchanged |
| `service-…@cloudcomposer-accounts` | `composer.serviceAgent`, `composer.ServiceAgentV2Ext` | Google-managed |

No Owner/Editor/broad-admin roles are granted to any Atlas identity. GitHub
authentication remains keyless (Workload Identity Federation, Sprint 4). The
QUARANTINE recovery used the development credential's pre-existing BigQuery
access for the targeted `DELETE`s; it required no new roles.

## Residual risks

- The development credential retains broad project access (documented since
  Sprint 4) and was used for recovery `DELETE`s. In a production model these
  would run under a scoped recovery identity with `bigquery.dataEditor` on the
  affected datasets only.
- Fault injection is dev-only by contract; there is no production kill-switch
  needed because the authorization chain refuses non-dev environments outright.
