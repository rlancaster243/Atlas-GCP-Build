# Sprint 4 Validation Report — Live Acceptance Evidence

Evidence-backed record of the Sprint 4 acceptance sequence (Phase 19).
Nothing below is claimed from static files alone; every row cites an
executed run, an audit record, or a preserved log.

Companion documents: `architecture-sprint4.md` (design),
`incident-report-sprint4.md` (gate demos + defect ledger),
`deployment-catalog-sprint4.md` (resource inventory),
`ci-cd-runbook-sprint4.md` (operator commands),
`ci-cd-governance-sprint4.md` (GitHub plan limitations).

## 1. Executive result

A clean Project Atlas change moved from an agent-created Git branch through
independent GitHub CI, keyless WIF authentication, an isolated integration
test, an immutable checksum-verified bundle, audited additive migrations, a
real Composer 3 deployment (`composer-3-airflow-3.1.7-build.13`), a 50 000-row
smoke batch with full warehouse reconciliation, a durable deployment audit
row, a deliberately failed defective deployment, and a live rollback that
restored and re-validated the prior release — with no manual code copying, no
stored service-account keys in GitHub, and no unverifiable runtime state.
The Composer environment was deleted immediately after evidence capture per
the ephemeral cost mandate (ADR-010).

## 2. Git and CI evidence

| Item | Value |
|---|---|
| Foundation PR | #14 (squash-merged `21d54ed`) — clean CI on run `29660771549` |
| Gate-demo PR | #15 (closed unmerged by design) — 4 deliberate failures, run IDs in `incident-report-sprint4.md` |
| Delivery PR | #16, branch `cursor/atlas-sprint-4-delivery-64a2` |
| Defect-demo branch | `cursor/atlas-sprint-4-defect-demo-64a2` @ `1af166e` (never merged; exists only as an immutable release for the rollback demo) |

## 3. Keyless authentication (WIF)

| Item | Value |
|---|---|
| Pool / provider | `atlas-github-pool` / `atlas-github-provider` (OIDC issuer `token.actions.githubusercontent.com`) |
| Trust condition | repository owner + exact repository `YOUR_GITHUB_OWNER/YOUR_REPOSITORY` + ref restriction |
| Identities | `atlas-github-integration` (isolated CI resources), `atlas-github-deployer` (deploy path) |
| Keys stored in GitHub | none — `id-token: write` + impersonation only |

IAM matrix and documented-risk notes: `ADR-009-workload-identity-federation.md`.

## 4. Isolated integration test (Phase 7)

`validate_gcp_integration.sh` executed live: run-scoped datasets
(`atlas_ci_<run>_…`) and GCS prefix, deterministic generation verified
byte-identical (after fixing defect D3), idempotent raw loading, dbt build
against isolated schemas, batch-scoped reconciliation, verified cleanup in an
always-running trap. No canonical dataset was written.

## 5. Deployment bundle (Phase 8)

| Item | Value |
|---|---|
| Released bundle (final) | `gs://atlas-deployments-example-gcp-project/atlas/releases/640cd78694a90275866bebbaf7550ee121fff79b/atlas-bundle.tar.gz` |
| Archive SHA-256 | `aaa83bc1578057e8f88b38f68aa9785a956099538f6ebf7aa69936c6575e6e7c` |
| Manifest | 314 files with per-file SHA-256, tool pins, `required_schema_version=003_create_deployments_table` |
| Immutability | create-only upload; content-identical retry reuses, different content fails |

## 6. Migrations (Phase 9)

Ledger `atlas_ops.schema_migrations` (all applied idempotently; reruns skip):

| migration_id | checksum (first 12) | status | applied_at (UTC) |
|---|---|---|---|
| `001_create_pipeline_runs_table` | `5fb06a83e1b3` | APPLIED | 2026-07-18 22:13:45 |
| `002_sprint3_raw_batch_columns` | `db8b53e68ee6` | APPLIED | 2026-07-18 22:13:49 |
| `003_create_deployments_table` | `d581c625ad1e` | APPLIED | 2026-07-18 22:13:52 |

## 7. Composer deployment (Phases 12–13)

| Item | Value |
|---|---|
| Environment | `atlas-dev`, us-central1, `composer-3-airflow-3.1.7-build.13`, small |
| Lifecycle | created ~22:05 UTC 2026-07-18, **deleted** ~01:35 UTC 2026-07-19 after evidence capture (ephemeral policy, ADR-010) |
| Successful deployment | `atlas-dev-20260719T005308Z-640cd786` → **SUCCESS** |
| Deployed SHA | `640cd78694a90275866bebbaf7550ee121fff79b` |
| Smoke DAG run | `smoke__atlas-dev-20260719T005308Z-640cd786` → Airflow terminal `success` |
| Smoke pipeline run | `atlas-smoke-640cd786-local1784422388-run` → `pipeline_runs.status=SUCCESS` (00:58:18 UTC) |
| Smoke validation | 12/12 checks PASS (dag import, no import errors, deployed SHA, terminal success, 50 000 raw rows, no duplicate load, GCS object, manifest, success marker, warehouse reconciliation, pipeline_runs, deployments row) |

Reaching SUCCESS took seven audited attempts; each failure exposed and fixed
a real defect (checksum-by-filename, Composer sys.path parity, stale import
errors, missing vendored dbt packages, Airflow 3 state parsing, rsync vs
deterministic mtimes). Full ledger: `incident-report-sprint4.md`.

## 8. Deliberate failed deployment + live rollback (Phases 14/16)

| Step | Evidence |
|---|---|
| Defective release | `1af166e` (`inject_failure: true` — dbt canary test fails) built and uploaded as a normal immutable bundle |
| Failed deployment | `atlas-dev-20260719T010538Z-1af166ea` → **FAILED**, `failure_stage=smoke_batch`; Airflow shows `dbt_build` failed, downstream `upstream_failed`; no success metadata published |
| Rollback | `rollback_atlas.sh` auto-selected newest prior SUCCESS (`640cd78`), verified manifest/checksums/schema compatibility, re-promoted |
| Rollback record | `atlas-dev-20260719T011614Z-640cd786` → **ROLLED_BACK**, `previous_git_sha=1af166e` |
| Rollback smoke | batch `atlas-smoke-640cd786-local1784423774`: 50 000 raw → 49 105 accepted + 895 rejected → 49 105 fact rows; `pipeline_runs.status=SUCCESS` (01:21:56 UTC); 12/12 smoke checks PASS |

Preserved logs: `evidence-sprint4/deploy-defective-1af166ea.log`,
`evidence-sprint4/rollback-640cd786.log`,
`evidence-sprint4/composer-deploy-session-history.txt`.

## 9. Deployment audit table (final state)

```text
deployment_id                        sha       type      status       failure_stage     previous
atlas-dev-20260718T225900Z-dd7dd5d4  dd7dd5d4  deploy    FAILED       fetch_release     —
atlas-dev-20260718T230144Z-2aeff26e  2aeff26e  deploy    FAILED       dag_parse         —
atlas-dev-20260718T231842Z-83c0d137  83c0d137  deploy    FAILED       dag_parse         —
atlas-dev-20260718T233128Z-74732eee  74732eee  deploy    FAILED       smoke_batch       —
atlas-dev-20260719T001246Z-f9959cb6  f9959cb6  deploy    FAILED       smoke_batch       —
atlas-dev-20260719T004112Z-37d4e6aa  37d4e6aa  deploy    FAILED       smoke_validation  —
atlas-dev-20260719T005308Z-640cd786  640cd786  deploy    SUCCESS      —                 —
atlas-dev-20260719T010538Z-1af166ea  1af166ea  deploy    FAILED       smoke_batch       —
atlas-dev-20260719T011614Z-640cd786  640cd786  rollback  ROLLED_BACK  —                 1af166ea
```

One row per attempt, controlled statuses, sanitized errors, rollback linked
to the SHA it replaced — exactly the Phase 10 contract.

## 10. Cost review

Composer small environment existed ~3.5 hours (creation → deletion), the
only meaningfully billable Sprint 4 resource. Remaining permanent resources
scale to zero: versioned deployment bucket (KB–MB scale), 7-day-TTL CI
bucket, BigQuery ops tables (MB scale), service accounts and WIF (free).

## 11. Honest limitations

- Branch protection / required reviewers unavailable on the GitHub Free
  plan; fallback governance documented in `ci-cd-governance-sprint4.md` and
  ADR-010. Completion gate 7 is satisfied via the documented-limitation arm.
- The successful deployment evidence was captured by executing the same
  repository scripts the GitHub workflows call (`deploy_atlas_release.sh`,
  `validate_atlas_deployment.sh`, `rollback_atlas.sh`) from the agent
  environment with ADC, because Composer create/delete cycles are gated on
  cost approval and the ephemeral environment was deleted after capture. The
  workflows themselves are exercised for auth and validation; a future
  GitHub-initiated deploy run requires only re-creating the environment
  (`manage_atlas_composer.sh create`) and dispatching `atlas-deploy.yml`.
- Composer worker logs did not surface in Cloud Logging during the capture
  window; failure diagnosis used the Airflow REST API, task-state listings,
  and BigQuery audit logs instead. Recorded as a Sprint 5 observability
  handoff item.
- The dbt warehouse rebuilds intermediate/fact tables scoped to the
  validated batch per run (Sprint 2 design), so cross-batch history in
  those tables reflects the newest build; per-run validation is performed at
  smoke time. Durable per-run evidence lives in `atlas_ops`.

## 12. Sprint 5 handoff (observability and alerting — requirements only)

Recorded per the Sprint 4 charter; none of this was implemented in Sprint 4:

- Centralized structured task logs — Composer worker logs did not surface in
  Cloud Logging during the Sprint 4 capture window (limitation above); Sprint 5
  must make task logs durably queryable before anything else.
- Pipeline and data freshness metrics (batch latency, last-success age per DAG).
- Failure alerts on `pipeline_runs.status=FAILED` and
  `deployments.status IN (FAILED, ROLLBACK_FAILED)`.
- Volume and schema monitoring (row-count drift per batch, schema-change detection
  against the migration ledger).
- Operational dashboards over `atlas_ops` (runs, deployments, migrations).
- On-call and escalation rules; incident-recovery drill cadence.
- SLO and error-budget candidates (smoke-run duration, deploy lead time,
  batch success rate).
- Stale-data detection (no successful batch within an expected window).
- Cost anomaly detection (Composer create/delete discipline, BigQuery scan
  volume, bucket growth).
