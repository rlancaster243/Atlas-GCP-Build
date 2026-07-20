# Atlas Sprint 6 Preflight — Resilience, Failure Engineering, Recovery, Game Days

Captured live on 2026-07-19 (UTC) before any Sprint 6 implementation or fault
injection. Every fact below was verified against the repository or the GCP
project `example-gcp-project`, not assumed from the execution prompt.

## 1. Git and release state

| Item | Verified value |
| --- | --- |
| origin/main | `078bc319c6683717e6583b4500af60b4dd3e168a` (matches prompt baseline) |
| Working tree | clean (`git status --porcelain` empty) |
| Sprint 6 branch | `cursor/atlas-sprint-6-resilience-64a2` (created from main; no other Sprint 6 branches or PRs exist) |
| Latest CI on main | run `29687038169` — atlas-ci **success** on Sprint 5 release commit `476e20a` |
| `atlas-sprint-1-complete` | `49a5fac` → `270e7d5` |
| `atlas-sprint-2-complete` | `1977983` → `5135778` |
| `atlas-sprint-3-complete` | `3f21d9d` → `8aa1d7a` |
| `atlas-sprint-4-complete` | `4251e94` → `b609ac1` |
| `atlas-sprint-5-complete` | `fd79562` → `476e20a2edcd9e6ae2e7aa2169d0f0c0fb13247c` (matches prompt) |
| Open PRs | #2, #3, #6 only — pre-Atlas scaffold, unrelated; no overlapping Atlas work |

## 2. GCP state

Active principal: `service1-831@example-gcp-project.iam.gserviceaccount.com`
(Cursor agent SA). Project: `example-gcp-project`.

### Composer
Absent, as expected (Sprint 5 ephemeral teardown 2026-07-19T07:37:56Z). No
orphaned Composer buckets. Environment-dependent alerts were intentionally
disabled before teardown and remain disabled — no false incidents.

### BigQuery datasets
`atlas_raw`, `atlas_staging`, `atlas_intermediate`, `atlas_quarantine`,
`atlas_core`, `atlas_marts`, `atlas_dbt_staging`, `atlas_ops`, `atlas_logs`
(linked, read-only).

### atlas_ops tables
`pipeline_runs`, `deployments`, `schema_migrations` (6 APPLIED),
`task_events` (176 rows), `quality_results` (60 rows),
`monitor_evaluations` (91 rows). Migration 007 (`recovery_actions`) is the
next free slot.

### GCS
`atlas-raw-events-…` (canonical raw), `atlas-deployments-…` (immutable
releases), `atlas-ci-…` (ephemeral CI).

### Logging (permanent, verified live)
Sink `atlas-observability-sink` → bucket `atlas-observability`
(us-central1, 30-day retention, analytics enabled), view `atlas-runtime`,
linked dataset `atlas_logs` queryable.

### Monitoring (permanent, verified live)
Dashboard `Atlas Operations` (`a4f0a238-90b5-445b-925e-d0922d343c2b`).
Notification channel `Atlas Primary Operator (email)`
(`6567861337166986657`). Ten alert policies present:

| Policy | Enabled |
| --- | --- |
| Atlas: pipeline failed | true |
| Atlas: data stale | **false** (disabled for teardown — re-enable with Composer) |
| Atlas: reconciliation failed | true |
| Atlas: critical volume deviation | true |
| Atlas: breaking schema drift | true |
| Atlas: deployment failed | true |
| Atlas: rollback failed | true |
| Atlas: Composer environment unhealthy | **false** (disabled for teardown — re-enable with Composer) |
| Atlas: BigQuery cost anomaly | true |
| Atlas: telemetry incomplete | true |

No open incidents; no `AlertPolicyViolation` entries since teardown.

### WIF / service accounts
Pool `atlas-github-pool` ACTIVE. SAs: `atlas-composer-runtime`,
`atlas-github-deployer`, `atlas-github-integration` (see §5 IAM table).

## 3. Baseline data (latest healthy state)

| Item | Value |
| --- | --- |
| Latest successful run | `atlas-drillb-20260719-recovery-run` (batch `atlas-drillb-20260719`), SUCCESS 06:58:00Z |
| Raw rows | 50,000 |
| Accepted / fact rows | 49,105 |
| Rejected | 895 (rate 0.0179) |
| Mart total events | 343,738 (reconciles) |
| Quality checks on latest run | 10/10 PASS |
| Latest deployment | `atlas-dev-20260719T061802Z-2109310b` SUCCESS (sha `2109310b`) |
| Latest FAILED deployment (expected, drill) | `atlas-dev-20260719T042523Z-8fe17dcd` |
| Migrations applied | 001–006 |
| Success marker | present for latest batch (verified during Sprint 5 acceptance) |
| Schema signatures | `observability/schema/expected-schemas.json` matches live tables (schema-drift monitor last evaluated PASS) |

## 4. Known limitations carried into Sprint 6

1. **Raw Airflow stdout**: Composer 3 `build.13` platform log-export defect;
   Atlas telemetry is mirrored directly via `ATLAS_LOG_TO_CLOUD_LOGGING=true`
   (`atlas-events` log). Phase 1 will re-test on the currently available image.
2. **Failed-task timing**: two `FAILED` task_events rows
   (`atlas-drillb-20260719-run`: `dbt_build`, `write_run_summary`) have NULL
   `started_at`/`completed_at`/`duration_ms` — the exact Phase 1 cleanup target.
   The failure-callback path records the terminal event without the timing that
   the success path gets from the runner wrapper.
3. **Email delivery latency**: notification evidence relies on operator
   confirmation (user confirmed receipt during Sprint 5); no programmatic
   mailbox access.
4. **Thresholds are synthetic-workload initial values**, not production SLOs.
5. **Single-operator model** (the primary operator primary; repo owner escalation).
6. **Cost attribution boundary**: job labels + runtime identity; dbt child jobs
   labeled via `query-comment`/`job-label`; console-issued ad-hoc queries are
   outside attribution.

## 5. Security / IAM snapshot (before any Sprint 6 change)

| Principal | Roles (project level) |
| --- | --- |
| `atlas-composer-runtime@…` | `composer.worker`, `bigquery.jobUser`, `bigquery.dataEditor`, `bigquery.resourceViewer` |
| `atlas-github-deployer@…` | `bigquery.jobUser`, `bigquery.dataEditor`, `composer.user`, `composer.environmentAndStorageObjectAdmin` |
| `atlas-github-integration@…` | `bigquery.jobUser`, `bigquery.dataEditor` |

- Secret scanning: enforced by `validate_ci.sh` gate (green on main).
- Fault-injection leak risk: scenarios must reuse the Sprint 5 sanitization
  (`error_message` redaction/truncation); no scenario may echo credentials,
  tokens, or raw payloads. Enforced by framework tests.
- Test-resource blast radius: all destructive scenarios use isolated batch IDs
  (`atlas-s6-*` prefix), isolated datasets/tables/prefixes, never canonical
  batches; the framework will refuse canonical batch IDs by construction.
- IAM scenarios (S6-IAM-*) remove exactly one role from one member, capture
  before/after policy, and restore the identical binding.

## 6. Cost plan

| Item | Estimate |
| --- | --- |
| Composer SMALL (us-central1) | ≈ $0.60–0.75/h; Sprint 5 window (3.9 h) cost ≈ $2.50 |
| Sprint 6 live window target | ≤ 12 h Composer runtime (five game days batched into one window), ceiling ≈ $9 |
| BigQuery | synthetic 50k-row batches ≈ MBs per query; cost drills use dry-run / `maximum_bytes_billed` only — no intentional spend |
| Logging/metrics | within Sprint 5 free-tier envelope (≈ 40 MB/day peak measured) |
| Teardown | Composer + drill fixtures deleted under `ATLAS_APPROVE_TEARDOWN`; permanent observability plane retained |

Maximum allowed live test duration: one Composer window ≤ 12 h; every scenario
carries `maximum_duration` and `maximum_cost` in `config/failure_scenarios.yaml`.

## 7. Approvals

Per the sprint owner's standing decisions (ephemeral Composer approved, IAM
approved at every stage, builds approved) the Sprint 6 approval set
(`ATLAS_APPROVE_PROVISION/IAM/COMPOSER_CREATE/FAILURE_INJECTION/`
`DESTRUCTIVE_FIXTURE/DEPLOY/ROLLBACK_TEST/ALERT_DRILLS/TEARDOWN=true`) is
treated as granted as stated in the execution prompt. Each gated mutation still
logs which approval it consumed; no approval is reinterpreted across categories.

## 8. Implementation sequence

1. **Phase 1** — failed-task timing (`timing_source`/`timing_confidence`,
   derive from callback context or STARTED row, never invent) + regression
   tests; Composer log re-test deferred to the live window.
2. **Phases 2–3** — failure catalog (`failure-catalog-sprint6.md`,
   `config/failure_scenarios.yaml`, ADR-013) and fault-injection framework
   (`scripts/run_failure_scenario.sh`, `src/atlas/failure_injection/`,
   disabled-by-default enforcement + tests).
3. **Phase 4** — migration 007 `recovery_actions` + `src/atlas/ops/recovery_actions.py` + tests.
4. **Phases 5–12 (static half)** — scenario logic and guards implementable
   without cloud: cost guards (dry-run byte ceiling, backfill window,
   full-refresh approval), schema classification extensions, IAM error
   classification, observability degradation paths, plus unit tests per
   Phase 16 matrix.
5. **Phases 13–14** — recovery runbook + ADR-014 + ADR-015 + game-day plan.
6. **Phase 16** — CI gates (scenario schema validation, fault-injection
   default-off check) and green static CI.
7. **Phase 17 live window** — recreate Composer (build.13 or newer compatible
   image), deploy candidate, baseline batch, Game Days 1–5 with recovery,
   reconciliation, and MTTR capture.
8. **Phases 15+18** — two incident reports, validation/cost/security reviews,
   README updates.
9. **Closeout** — disable fixtures, teardown, final CI, merge, tag
   `atlas-sprint-6-complete`.

No cloud resource is provisioned and no fault is injected until steps 1–6 are
green in CI.
