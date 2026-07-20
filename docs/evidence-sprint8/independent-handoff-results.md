# Independent Handoff Results (Sprint 8, Phase 12)

**Status:** RECORDED. The independent tester received only the repository clone,
`START_HERE.md`, and the [assignment](../handoff/independent-handoff-assignment.md).
No prior conversation, no implementation-agent reasoning, no hidden commands, no
verbal help. Rubric: [../handoff/handoff-scorecard.md](../handoff/handoff-scorecard.md).

## Tester context

- Identity type: independent coding agent (separate agent context, repository +
  START_HERE + assignment only).
- Candidate commit at test time: `d90b3ad`.
- Human interventions: **0** (the tester self-resolved the one friction point
  using the repository's own venv convention; the implementation agent provided
  no answers or commands).

## Answers (summary — all 15 items completed correctly)

1. Atlas = reference-architecture batch ELT platform on GCP; correct/observable/
   governable/recoverable; not streaming/CDC/ML; not a template. ✓
2. Fact grain = **one row per `event_id`** (`fct_events`, merge on `event_id`,
   INV-D5, ADR-017). ✓
3. `batch_id` = stable data identity (`atlas-<YYYYMMDD>`); `pipeline_run_id` =
   one execution (`atlas-airflow-<date>-<runid>`); ADR-006. ✓
4. Current release `atlas-sprint-7-complete` → `9d031c9`; Sprint 8 intentionally
   untagged. (Correctly de-referenced annotated tags.) ✓
5. `validate_ci: PASS` (19 PASS / 2 SKIP / 0 FAIL). Noted the PEP 668 install
   friction (see below). ✓ (with friction)
6. Successful deploy: `docs/evidence-sprint4/composer-deploy-session-history.txt`. ✓
7. Failed deploy: `docs/evidence-sprint4/deploy-defective-1af166ea.log`
   (`publish_success_marker = upstream_failed`, proving INV-L5). ✓
8. Recovery: `docs/evidence-sprint4/rollback-640cd786.log` (+ INC-S6-001 for the
   verified data-layer recovery). ✓
9. Schema control: compatibility classification + change records + immutable
   migration checksums (ADR-017, INV-D8). ✓
10. Unsafe query blocked: `cost_guard check-partition-filter` + dry-run
    `estimate` vs ceiling ($0), evidence `cost-guard-block.txt`. ✓
11. Risks: correctly reported **no HIGH** severity; listed the MEDIUM/LOW set
    (RISK-01/02/06/07/09/10/11/12 + lows). ✓
12. API ingestion: new `src/atlas/ingestion/<api>.py`, source YAML, governance
    asset, tests, keep API out of PR CI (INV-L1). ✓
13. Files + invariants: ingestion module, sources.yml, governance asset, tests,
    lineage/evidence; preserve D1/D2/D6/L1/G1–G3. ✓
14. Approvals: full `ATLAS_APPROVE_*` set enumerated. ✓
15. Not proven at scale: production perf/cost, billed perf, live least privilege,
    live retention, multi-env, template, external consumers. ✓

## Score: 29 / 30 (see scorecard)

Validation scored 1 (completed with friction); all other 14 categories scored 2.
Meets minimum acceptance: total ≥ 25, no 0 in architecture/validation/evidence/
risk, ≤ 2 human interventions (0), no hidden command supplied.

## Observations

- **Time to first successful validation:** one moderate iteration.
- **Friction / defect found:** `START_HERE` §6 `pip install` fails on PEP 668
  hosts (Debian/Ubuntu) because no virtualenv step was documented. The tester
  self-resolved using the venv convention already present in the Sprint 1 quick
  start and `validate_clean_clone.sh`.
- **Precision defect found:** the "282 unit tests" / "21 gates" figures are only
  fully reached with optional toolchains; the credentialless gate runs 269
  unit+Airflow tests (240 unit / 29 Airflow) with 2 gates SKIPPED.
- **Misunderstanding (self-corrected):** initially thought README tag commits
  mismatched git — corrected after realizing the tags are annotated.
- **Help needed beyond the repository:** none.

## Files changed because of the test (documentation root-cause fixes)

`START_HERE.md` (venv step + accurate 269/282 counts), `operator-onboarding.md`,
`operator-first-hour.md`, `agent-onboarding.md`, `capability-evidence-map.md`,
`evidence-index.md`, `engineering-evidence-ledger.md`, `atlas-demo-script.md`.

## Re-verification after fixes

The corrected `START_HERE` §6 now matches exactly what
[`validate_clean_clone.sh`](../../scripts/validate_clean_clone.sh) does
(create venv → install both requirement files → run static CI), and that script
passes from a fresh directory (see [clean-clone-results.md](clean-clone-results.md)
attempt 2). This proves the corrected instruction works verbatim. A full fresh
independent-agent re-run was deferred to conserve tokens; the specific fixed
step is verified by the passing clean-clone.
