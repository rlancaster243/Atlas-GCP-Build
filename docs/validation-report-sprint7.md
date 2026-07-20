# Atlas Sprint 7 Validation Report — Governance, Contracts, Schema Evolution, Security, Performance, Cost

Every claim below is backed by one of: a committed artifact in this repository,
a green CI gate in `scripts/validate_ci.sh`, a unit/dbt test, or a bounded live
GCP dry-run (billing $0) in project `example-gcp-project`. Gated live
mutations that were **not** approved are recorded as blocked gates, not as
proof. Documentation is never treated as live evidence.

## 1. Git and release evidence

| Item | Value |
| --- | --- |
| Sprint 6 completion tag | `atlas-sprint-6-complete` → `48da9d226e0e942095c0623e5bd71d06f5e32e36` (matches prompt) |
| Sprint 7 base (origin/main) | `48da9d2` (+ `1c2cc15` release-row doc) |
| Sprint 7 branch / PR | `cursor/atlas-sprint-7-governance-64a2` / PR **#22** |
| Prior CI failure (pre-fix) | run `29702642835` — `atlas-security-shell` FAIL (`secret_scan` flagged its own fixtures) |
| Fix | `7f0eff6` — allowlist `test_security_policy.py` in `gate_secret_scan` (mirrors `test_audit.py`) |
| Local static CI after fix | `validate_ci.sh --mode static` = **PASS** (all runnable gates green) |
| GitHub CI on final branch head `cb85c3c` | run **`29702939614`** — atlas-ci **success** (atlas-python, atlas-dbt, atlas-security-shell, atlas-airflow, atlas-ci-gate all green) |
| Final merge SHA / tag | recorded at closeout (Phase 16 steps 40–42), after merge to main (awaiting merge authorization) |

Sprint 1–6 tags are unchanged. `atlas-sprint-7-complete` is created only after
green GitHub CI on the merged main commit (completion gate 34).

## 2. Token-efficiency result

Proxy ledger (`docs/token-efficiency-sprint7.md`): **1** full repository scan
(Phase 0), **0** Composer create/delete cycles, **0** live deployment cycles,
**0** major plan regenerations. Composer was proven unnecessary for Sprint 7
controls (governance/schema/lineage/security/retention/perf/cost are provable
offline or via BigQuery dry-run + IAM read APIs), consistent with the preflight
expectation and the 55–75%-of-Sprint-6 envelope. No scope-compression tripwire
was triggered.

## 3. Sprint 6 inherited limitations — disposition

| Inherited limitation | Sprint 7 disposition |
| --- | --- |
| Batch-scoped anomaly profile sensitive to same-date reprocessing (INC-S6-001) | **Resolved** (Phase 3): within-batch vs cross-batch replay now distinguished; anomaly assertion counts `is_within_batch_duplicate` only |
| Live game-day coverage a representative subset | Out of scope for Sprint 7; governance controls proven by gates + fixtures |

## 4. Governance architecture and one source of truth (gates 2–3)

- dbt models carry authoritative `meta.governance` (purpose/grain/owner/
  classification/retention/contract/consumers/lifecycle); non-dbt assets live in
  `governance/non_dbt_assets.yml`. No third manual copy — `gate_governance`
  rejects a duplicate source of truth.
- Consolidated catalog generated from those sources:
  `python -m atlas.governance.catalog check` → *"governance catalog matches
  sources"*, **22 assets**, all with a technical owner and (for models) a grain.

## 5. Contracts and schema compatibility (gates 7–11)

- Data-contract standard + boundary map: `docs/data-contract-standard-sprint7.md`
  (ADR-016). Contracts map to executable controls (dbt contracts, tests, JSON
  schema, Python validation, CI).
- `atlas.governance.schema_check` classifies changes COMPATIBLE /
  CONDITIONALLY_COMPATIBLE / BREAKING / PROHIBITED against a committed
  `governance/schemas/manifests/baseline.json` (ADR-017).
- Applied-migration immutability: `sql/migrations/checksums.lock`;
  `gate_schema_compatibility` fails on any checksum change.
- Evidence (fixtures, no defect merged): additive nullable → COMPATIBLE
  (`test_added_nullable_field_is_compatible`); breaking type change → BREAKING
  (`test_type_change_is_breaking`); checksum tamper detected
  (`test_migration_checksum_tamper_is_detected`).

## 6. Duplicate and replay semantics (gates 12–15)

Phase 3 resolves the Sprint 6 defect while preserving the **one-row-per-event_id**
`fct_events` grain (ADR-006 amendment):

- `within_batch_duplicate_rank` (latest-wins within a batch) vs global
  `duplicate_rank` (first-seen-batch-wins) with `duplicate_scope` ∈
  {`none`, `within_batch`, `cross_batch_replay`}.
- Exact rerun stays idempotent (fct merge `unique_key`); same date under a
  different batch classified as `cross_batch_replay`; 50 intentional within-batch
  extras remain detectable; global fact uniqueness enforced; accepted+rejected
  reconciles to raw.
- Live dbt tests PASS: `test_cross_batch_replay_preserves_first_seen`,
  `test_duplicate_ranking_keeps_latest_canonical`.

## 7. Lineage and consumer impact (gates 16–17)

- `atlas.governance.lineage` builds the graph from dbt `ref()`/`source()` +
  `consumers.yml`; committed `governance/generated/lineage.json`
  (**26 nodes, 29 edges**, source→mart intact, verified by `gate_lineage_impact`).
- `atlas.governance.impact` reports direct/transitive downstream assets, affected
  tests/contracts, consumers, owners-to-notify, and runbooks
  (`test_impact_identifies_downstream_models`). No graph DB / metadata service.

## 8. Deprecation lifecycle (gate 18)

`ACTIVE → DEPRECATED → REMOVAL_SCHEDULED → REMOVED` enforced in
`registry.deprecation_errors()`; CI rejects deprecation without replacement,
removal before the minimum window, and removed assets with active consumers
(`test_deprecated_without_replacement_fails`,
`test_removed_asset_with_active_consumer_fails`). Runbook:
`docs/deprecation-runbook-sprint7.md`.

## 9. IAM review (gates 19–22)

- Inventory + evidence matrix: `docs/iam-review-sprint7.md` (ADR-018). Keyless
  WIF only; no Owner/Editor/SA keys; prohibited patterns enforced by
  `gate_security_policy` (`scan_managed_iam`).
- One justified reduction candidate identified: `atlas-github-integration`
  project-level `roles/bigquery.dataEditor` is broader than required; a scoped
  reduction + positive/negative test plan is documented.
- **Blocked gate:** live IAM reduction and positive/negative tests require
  `ATLAS_APPROVE_IAM=true` (not set). Recorded, not weakened, not faked. Gate 20
  is satisfied by a documented, evidence-backed reduction plan pending approval.

## 10. Security and data-exposure review (gate 23)

`docs/security-review-sprint7.md`: no committed/untracked credentials, no secrets
in logs or audit error fields, no real user data. `scan_data_exposure` +
`scan_managed_iam` run in `gate_security_policy`; the scanner reports *reasons*,
never values (`test_security_policy.py`). Public-repository extraction risks are
cataloged for Sprint 8 (repo not published in Sprint 7).

## 11. Classification and retention (gates 5–6, 24–25)

`governance/classifications.yml` (PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED, no
RESTRICTED assets present) and `governance/retention.yml`
(canonical/operational/temporary/release/test-fixture) validated by
`atlas.governance.retention.validate_retention_config` inside `gate_governance`
(ADR-019). Permanent evidence cannot be given an expiration; transient classes
must have one; conflicting policies fail CI (`test_retention.py`). Live
expiration application is gated on `ATLAS_APPROVE_RETENTION_MUTATION` (not set):
disposal is a dry-run plan only (`plan_expirations`).

## 12. BigQuery performance baseline (gates 26–27)

`scripts/run_performance_suite.sh` + `observability/performance/queries/` (9
representative queries). Dry-run baseline `results/baseline-dryrun.json`: every
query well under the 1 GiB per-query ceiling (largest 34.4 MB `08_cost_monitor`;
mart aggregation 44.9 KB). Partition pruning demonstrated (bounded 2.3 MB vs
unbounded 12.7 MB). Conclusion — evidence-backed **"no material change
warranted"** (`docs/performance-review-sprint7.md`); no optimization made merely
to produce a percentage. **Blocked gate:** executed (billed) suite requires
`ATLAS_APPROVE_PERFORMANCE_TESTS=true` / `ATLAS_MAX_PERFORMANCE_TEST_BYTES`
(not set).

## 13. Cost controls (gate 28)

`config/cost_controls.yaml` (per-env ceilings, partition-filter requirements,
TTLs) + `atlas.observability.cost_guard` (ADR-020). Live dry-run block evidence
(`docs/evidence-sprint7/cost-guard-block.txt`, billed **$0**): a deliberately
unbounded `atlas_raw.events` scan is refused before spend by (a) the
required-partition-filter guard (exit 2) and (b) the dry-run estimate ceiling.

## 14. CI enforcement (gates 13, 29) and controlled demonstrations

Five focused offline gates run in the `python` group and are wired into
`.github/workflows/atlas-ci.yml` with no duplicated logic: `gate_governance`,
`gate_schema_compatibility`, `gate_lineage_impact`, `gate_security_policy`,
`gate_performance_cost`. The 16 required controlled demonstrations are mapped in
`docs/governance-demos-sprint7.md`; 14 are proven offline / via live dbt tests
and pass in CI (**282 tests collected**); #11 is the live dry-run cost block;
#13–14 are the gated live IAM tests above.

## 15. Live GCP evidence and cleanup (gates 30–31)

Bounded live window used read-only IAM inventory and BigQuery **dry-run**
estimates only (billed $0). No Composer created (not required). No temporary
datasets/buckets created, so no teardown needed. Canonical Atlas data is
untouched by Sprint 7 (governance overlay + classification-semantics fix only);
the healthy baseline continues to reconcile under the declared grain.

## 16. Documentation inventory (gate 32)

All Phase 17 artifacts present: preflight, context pack, token-efficiency,
architecture, governance-model, data-contract-standard, schema-evolution-policy,
lineage-impact, deprecation-runbook, iam-review, security-review,
retention-policy, performance-review, cost-review, and this validation report.
ADR-016 through ADR-020 present (ADR-006 amended for replay semantics). README
updated (release-tag table, governance/perf commands, Sprint 8 handoff).

## 17. Scope adherence (gate 33)

`transform/dbt/**`. No new platform, catalog service, external policy engine, or
second repository. Reusable-template extraction and reference-architecture
packaging are explicitly deferred to Sprint 8.

## 18. Blocked completion gates (honest limitations)

The following require operator approval variables that are **not set**; they are
implemented statically with exact live plans and recorded as blocked, per the
prompt's missing-approval behavior:

| Gate | Approval required | Status |
| --- | --- | --- |
| Live IAM reduction + positive/negative test (demos #13–14) | `ATLAS_APPROVE_IAM=true` | Plan complete; blocked |
| Executed (billed) BigQuery performance suite | `ATLAS_APPROVE_PERFORMANCE_TESTS=true` (+ byte ceiling) | Dry-run done; execution blocked |
| Live retention/expiration application | `ATLAS_APPROVE_RETENTION_MUTATION=true` | Dry-run plan done; application blocked |

No live proof is claimed for these. No gate was weakened to pass. Sprint 7 does
not claim enterprise-wide governance, regulatory certification, production-scale
performance from a ~50k-row dataset, complete least privilege without
permission-level negative-test evidence, full consumer discovery outside the
repository, zero-cost operation, or public-repository readiness (Sprint 8).

## 19. Completion-gate summary

Gates 1–19, 23–29, 31–33 are met with committed artifacts, green CI, and $0
live dry-run evidence. Gate 20 is met by a documented, evidence-backed reduction
plan pending `ATLAS_APPROVE_IAM`. Gates 21–22 (live positive/negative IAM),
24 (live retention application), and 30 (temporary-resource teardown — none
created) are blocked or not-applicable as recorded above. Gate 34
(`atlas-sprint-7-complete` on the validated merge commit) is completed at
closeout after green GitHub CI on merged main.
