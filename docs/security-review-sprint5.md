# Atlas Sprint 5 Security Review

Scope: the observability additions of Sprint 5 — structured logging, audit
tables, log routing, linked dataset, metrics, alerting, dashboard, and the
drills. Reviewed live on 2026-07-19 against project `example-gcp-project`.

## Log content safety

| Control | Evidence |
| --- | --- |
| No secrets in structured events | `emit_event` builds from a fixed field allowlist; `error_message` passes through `sanitize_error_message` (the Sprint 4-audited sanitizer: strips bearer tokens, key material patterns, long opaque strings) and is truncated at 2 000 chars; `details` truncated at 4 KB. Unit-tested in `tests/unit/test_observability_logging.py` (redaction, truncation, non-serializable degradation). |
| No raw event payloads | Only counts, ids, and bounded details fields are emitted; the event generator's payloads never enter telemetry. |
| No full SQL text | Cost attribution uses job labels and `INFORMATION_SCHEMA` aggregates; `details_json` in audit tables stores summaries only. |
| No environment dumps | The contract has no field capable of carrying `os.environ`; unknown fields are dropped (or rejected in strict mode). |
| Live spot-check | Drill artifacts in `docs/evidence-sprint5/` were reviewed; the notification-channel evidence stores only the email domain, not the address. |

## IAM evidence table (live `gcloud projects get-iam-policy`, 2026-07-19)

| Principal | Roles | Purpose / justification |
| --- | --- | --- |
| `atlas-composer-runtime@…` | `roles/composer.worker`, `roles/bigquery.jobUser`, `roles/bigquery.dataEditor`, `roles/bigquery.resourceViewer` | Composer 3 runtime identity. `composer.worker` already includes `logging.logEntries.create` and `monitoring.timeSeries.create`, so **no new logging/monitoring roles were required** for structured emission or metric publication. `resourceViewer` was added during acceptance because the cost check reads `region-us.INFORMATION_SCHEMA.JOBS` (needs `bigquery.jobs.listAll`); it is read-only metadata access. |
| `atlas-github-integration@…` | `roles/bigquery.jobUser`, `roles/bigquery.dataEditor` | unchanged from Sprint 4 (isolated CI datasets); no Sprint 5 broadening |
| `atlas-github-deployer@…` | `roles/bigquery.jobUser`, `roles/bigquery.dataEditor`, `roles/composer.user`, `roles/composer.environmentAndStorageObjectAdmin` | unchanged from Sprint 4; no Sprint 5 broadening |
| `service-…@cloudcomposer-accounts` | `roles/composer.serviceAgent`, `roles/composer.ServiceAgentV2Ext` | Google-managed Composer service agent (standard) |
| `service-…@gcp-sa-logging` | `roles/logging.serviceAgent` | Google-managed Log Router service agent — this is the sink writer identity for the `atlas-observability` bucket (intra-project sinks use the Logging service account; no custom writer identity was created) |

No Owner/Editor/broad admin roles were granted to any Atlas identity. The
Cursor development credential retains its pre-existing project access
(documented since Sprint 4) and was used for drill fixtures.

## Logging and Monitoring access boundary

- The `atlas-runtime` log view exists for least-privilege consumption; access
  is granted per-view via `roles/logging.viewAccessor` (no grants exist yet —
  there are no third-party readers).
- **Documented boundary expansion:** the `atlas_logs` linked BigQuery dataset
  makes log entries readable to anyone with BigQuery read on that dataset,
  bypassing Logging IAM. Mitigations: the dataset is read-only by
  construction, no dataset-level grants were added, and the routed content is
  contract-sanitized. This trade-off is accepted for queryability and
  documented in ADR-011.
- No unrestricted `roles/logging.privateLogViewer` grants exist.
- Data-access audit logs for BigQuery remain enabled (pre-existing) and are
  the largest log source; they contain identities and query metadata but no
  Atlas payload data.

## Notification and alerting safety

- Single email channel, created only after the owner supplied the address
  in-session (`ATLAS_APPROVE_ALERT_CHANNEL` flow); the address is not
  committed anywhere in the repository — alert policy JSONs carry a
  `${NOTIFICATION_CHANNEL}` placeholder that is resolved at apply time from
  `ATLAS_NOTIFICATION_CHANNEL_ID`.
- Alert documentation fields contain runbook paths and bounded metric
  descriptions; CI (`observability_config` gate) rejects committed channel
  ids, secrets, or unresolved runbook anchors.
- Test incidents carry only check names and threshold numbers.

## CI and deployment boundary (unchanged from Sprint 4, re-verified)

- Pull-request CI remains credentialless: `atlas-ci.yml` has no GCP
  authentication and read-only workflow permissions.
- Cloud mutations run only from trusted workflows/scripts behind WIF with the
  dedicated deployer identity, or from the operator's session behind the
  `ATLAS_APPROVE_*` variables.
- The deployment bundle excludes notification addresses, channel ids, drill
  payloads, and evidence logs (`build_deployment_bundle.sh` allowlist; the
  new `observability/metrics` and `observability/schema` assets are static
  catalogs).

## Residual risks

1. The linked-dataset boundary expansion described above (accepted,
   documented).
2. `ATLAS_LOG_TO_CLOUD_LOGGING=true` gives runtime code a direct write path
   to Cloud Logging. The writer permission already existed via
   `composer.worker`; the env var only activates client usage. Contract
   sanitization applies to every event on this path.
3. Drill-mode metric points share the alert policies with normal series
   (deliberate — drills must prove the real policies). A malicious or
   accidental publisher with `monitoring.timeSeries.create` could open false
   incidents; acceptable in a single-operator development project.
