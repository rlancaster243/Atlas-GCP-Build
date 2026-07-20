# Atlas Security & Data-Exposure Review (Sprint 7)

Validates that Atlas commits no secrets or sensitive data and that managed IAM
definitions grant no prohibited roles. Enforced by `gate_secret_scan` (existing)
and `gate_security_policy` (Sprint 7). See ADR-018 for IAM boundaries.

## Scope

Governed Atlas artifacts: `config/`, `governance/`, `observability/`, `scripts/`,
`src/atlas/`, `sql/`, `dags/`, `docs/`. Out-of-scope trees
(Sprint 8).

## Checklist results

| Check | Result |
| --- | --- |
| No committed credentials (private keys, API keys, SA JSON) | PASS (`gate_secret_scan` + `scan_data_exposure`) |
| No untracked credential files in the worktree | PASS (`gate_secret_scan`) |
| No secrets in immutable release bundles | PASS (bundle build excludes credentials; ADR-010) |
| No secrets in structured logs | PASS (field allowlist + truncation, Sprint 5) |
| No secrets in audit error fields | PASS (`sanitize_error_message`, Sprint 4) |
| No Authorization headers with literal tokens | PASS (`bootstrap_observability.sh` uses `Bearer $token` variable) |
| No committed private webhook URLs | PASS (alert JSON uses `${NOTIFICATION_CHANNEL}` placeholder) |
| No committed notification verification data | PASS (only placeholders committed) |
| No real user data | PASS (all event data is synthetic via `generate_events`) |
| No prohibited IAM roles in managed scripts | PASS (`scan_managed_iam` — 0 findings) |
| No service-account key creation | PASS (keyless WIF only) |

## Discovered gap → regression control

- **Managed-IAM scanner:** new `scan_managed_iam` fails CI if any Atlas bootstrap
  script ever grants `roles/owner`/`roles/editor`/`projectIamAdmin` or creates a
  service-account key. This converts the ADR-018 prohibition into an enforced
  regression test.
- **Data-exposure scanner:** new `scan_data_exposure` fails CI on literal
  secrets, Slack webhooks/tokens, literal bearer tokens, or personal email
  addresses in governed artifacts, while explicitly allowing variable
  references. Regression tests in `tests/unit/test_security_policy.py`.

## Public-repository extraction risks (resolved in the template extraction)

1. **Operator identity:** fixture actor/owner data was replaced with
   `<operator-email>` before public extraction.
2. **Project and pool identifiers:** source sandbox values were replaced with
   documented examples or runtime configuration.
3. **Notification recipient address:** remains external to Git and is configured
   through the target environment.

## Honest limitations

- The scanners are pattern-based; they catch the known credential and
  exposure shapes, not every conceivable secret format.
- Each adopter must rerun the security and public-extraction gates against its
  own configuration and deployment evidence.
