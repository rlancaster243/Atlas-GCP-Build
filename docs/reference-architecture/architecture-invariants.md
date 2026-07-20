# Architecture Invariants

**Status:** CURRENT · **Audience:** engineer, agent, reviewer. These are the
properties that must remain true. Each has an id, statement, reason, enforcement,
evidence, failure consequence, safe-change procedure, and related ADRs. An agent
must confirm no invariant is silently broken (see
[agent-task-protocol.md](../handoff/agent-task-protocol.md)).

Format per entry: **INV — statement** · *why* · **enforced by** · *evidence* ·
**if broken** · *safe change* · ADRs.

## DATA

- **INV-D1 — Raw artifacts are immutable and run-scoped.** *Reproducibility &
  audit.* Enforced by create-only GCS upload paths + loader. Evidence:
  `validation-report-sprint1.md`. If broken: history becomes unauditable. Safe
  change: new run prefix, never overwrite. ADR-003.
- **INV-D2 — `batch_id` is stable data identity; `pipeline_run_id` is one
  execution.** *Separates data from run.* Enforced by `src/atlas/batch` run
  context + `atlas_ops.pipeline_runs`. Evidence: `validation-report-sprint3.md`,
  ADR-006/007. If broken: reruns duplicate or lose data. Safe change: ADR + tests.
- **INV-D3 — Exact reruns are idempotent.** *Retries/backfills must be safe.*
  Enforced by dbt incremental `unique_key` + create-only loads. Evidence: dbt
  `test_duplicate_ranking_keeps_latest_canonical`. If broken: double counting.
  Safe change: preserve merge key. ADR-006.
- **INV-D4 — Within-batch duplicates and cross-batch replay are distinct.**
  *Anomaly profile vs replay must not conflate.* Enforced by
  `int_event_classification` (`within_batch_duplicate_rank` vs `duplicate_rank`,
  `duplicate_scope`). Evidence: dbt `test_cross_batch_replay_preserves_first_seen`.
  If broken: Sprint 6 INC-S6-001 recurs. Safe change: ADR-006 amendment procedure.
- **INV-D5 — `fct_events` grain is one row per `event_id`.** *Global uniqueness.*
  Enforced by dbt uniqueness test + merge key. Evidence: `core.yml` tests. If
  broken: all downstream metrics wrong. Safe change: deliberate ADR only. ADR-006.
- **INV-D6 — accepted + rejected reconciles to raw under declared semantics.**
  *No silent data loss.* Enforced by reconciliation tests + `assert_source_*`.
  Evidence: `validation-report-sprint2.md`. If broken: data leakage. Safe change:
  update contract + tests together.
- **INV-D7 — Quality failure prevents publication.** *No bad data downstream.*
  Enforced by DAG quality gate + `atlas_ops.quality_results`. Evidence:
  game-day S6-DBT-002. If broken: consumers see bad data. Safe change: keep gate
  before publish step.
- **INV-D8 — Applied migrations are immutable.** *Deterministic schema history.*
  Enforced by `gate_schema_compatibility` + `sql/migrations/checksums.lock`.
  Evidence: `test_migration_checksum_tamper_is_detected`. If broken: drift. Safe
  change: add a new migration, never edit an applied one. ADR-017.

## DELIVERY

- **INV-L1 — PR CI remains credentialless.** *Untrusted PRs never touch GCP.*
  Enforced by `validate_ci.sh --mode static` + workflow separation. Evidence:
  green PR runs. If broken: supply-chain risk. Safe change: keep cloud in trusted
  workflows only. ADR-008.
- **INV-L2 — Trusted GCP actions use keyless WIF.** *No service-account keys.*
  Enforced by workflow OIDC + `gate_security_policy` (no key creation). Evidence:
  ADR-009, `validation-report-sprint4.md`. If broken: credential leakage. Safe
  change: never add SA keys; don't weaken trust conditions. ADR-009/018.
- **INV-L3 — Releases are immutable.** Enforced by content-pinned bundles
  (`build_deployment_bundle.sh`). Evidence: `deployment-catalog-sprint4.md`. If
  broken: non-reproducible deploys. Safe change: new bundle per release.
- **INV-L4 — Migrations run before deployment validation.** Enforced by deploy
  sequence. Evidence: sprint4/6 validation reports. If broken: schema/code skew.
  Safe change: preserve ordering. ADR-010.
- **INV-L5 — Smoke validation gates success; a failed deployment cannot publish
  success.** Enforced by `validate_atlas_deployment.sh` + `atlas_ops.deployments`.
  Evidence: sprint4 incident report. If broken: false green. Safe change: keep
  smoke gate mandatory.
- **INV-L6 — Rollback checks schema compatibility.** Enforced by
  `rollback_atlas.sh` + schema-version handling. Evidence: ADR-015. If broken:
  rollback corrupts schema. Safe change: keep compatibility check.
- **INV-L7 — Composer is ephemeral for evidence capture** (unless a future ADR
  changes it). Enforced by create/teardown procedure + `ATLAS_APPROVE_*`.
  Evidence: sprint6 teardown record. If broken: cost + drift. Safe change: ADR.
  ADR-005/010.

## OPERATIONS

- **INV-O1 — Operational history is durable.** `atlas_ops.*` tables persist
  through teardown. Evidence: sprint6 validation §8. Safe change: never expire
  audit tables (INV-G7).
- **INV-O2 — Failures are correlated by identifiers.** `pipeline_run_id` +
  `batch_id` on every event/log. Evidence: ADR-011. Safe change: keep correlation
  ids in the log contract.
- **INV-O3 — Recovery success requires verification.** SUCCESS gated on
  `VERIFIED` in `atlas_ops.recovery_actions`. Evidence: INC-S6-001. ADR-014.
- **INV-O4 — Fault injection is disabled by default.** Enforced by
  `gate_failure_injection` + config. Evidence: `test_failure_injection.py`. If
  broken: accidental production faults. ADR-013.
- **INV-O5 — Cost guards execute before expensive behavior.** Enforced by
  `cost_guard` dry-run-first. Evidence: `cost-guard-block.txt`. ADR-020.
- **INV-O6 — Alerts map to runbooks.** Enforced by `gate_reference_handoff`
  (alert→runbook) + observability config. Evidence: `alert-catalog-sprint5.md`.
- **INV-O7 — Teardown must not destroy required evidence.** Evidence: sprint6
  teardown preserved audit tables + recovery row. Safe change: teardown allow-list.

## GOVERNANCE

- **INV-G1 — Model governance metadata has one source of truth** (dbt `meta` for
  models, registry for non-dbt). Enforced by `gate_governance` duplicate check.
  ADR-016.
- **INV-G2 — All major assets have owners.** Enforced by `gate_governance`.
- **INV-G3 — All major models declare grain.** Enforced by `gate_governance`.
- **INV-G4 — Schema changes are classified** (COMPATIBLE/CONDITIONAL/BREAKING/
  PROHIBITED). Enforced by `schema_check` + `gate_schema_compatibility`. ADR-017.
- **INV-G5 — Breaking changes require migration + consumer-impact evidence.**
  Enforced by change-record requirement. Evidence: `test_schema_check.py`. ADR-017.
- **INV-G6 — Deprecation follows a controlled lifecycle.** Enforced by
  `registry.deprecation_errors`. Evidence: `test_deprecation.py`. ADR-017.
- **INV-G7 — Permanent evidence cannot receive transient retention.** Enforced by
  `retention.validate_retention_config`. Evidence: `test_retention.py`. ADR-019.
- **INV-G8 — Secrets are never written into evidence.** Enforced by `secret_scan`
  + `gate_security_policy` + `validate_public_extraction.py`. Evidence:
  `security-review-sprint7.md`. ADR-018.

## REFERENCE (Sprint 8)

- **INV-R1 — Repository instructions must not depend on prior conversations.**
  Enforced by `gate_reference_handoff` (forbidden-phrase scan). Evidence:
  clean-clone + handoff results.
- **INV-R2 — Current documentation identifies its verification commit.** Enforced
  by manifest `last_verified_commit` + evidence `verification_commit`. Enforced by
  `atlas.reference.validate`.
- **INV-R3 — Claims link to evidence.** Enforced by evidence index +
  `atlas.reference.validate`.
- **INV-R4 — Blocked work remains visibly blocked.** Enforced by evidence-index
  BLOCKED checks + `gate_reference_handoff`. Evidence: `unresolved-risks.md`.
- **INV-R5 — Reference architecture must not claim template status.** Enforced by
