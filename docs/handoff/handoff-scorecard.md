# Handoff Scorecard

**Status:** CURRENT · **Audience:** reviewer. Rubric for scoring the
[independent handoff assignment](independent-handoff-assignment.md). Filled-in
results (with the tester's answers) are in
[../evidence-sprint8/independent-handoff-results.md](../evidence-sprint8/independent-handoff-results.md).

## Scale

`0` = failed or required direct coaching · `1` = completed with friction or
ambiguity · `2` = completed independently and correctly.

## Categories (15, max 30)

Filled-in scores below are from the run recorded in
[../evidence-sprint8/independent-handoff-results.md](../evidence-sprint8/independent-handoff-results.md)
(candidate `d90b3ad`).

| # | Category | Score (0–2) |
| --- | --- | --- |
| 1 | found starting point | 2 |
| 2 | architecture comprehension | 2 |
| 3 | data-grain comprehension | 2 |
| 4 | identity semantics (`batch_id` vs `pipeline_run_id`) | 2 |
| 5 | validation success | 1 (PEP 668 install friction, self-resolved) |
| 6 | evidence discovery | 2 |
| 7 | deployment comprehension | 2 |
| 8 | recovery comprehension | 2 |
| 9 | governance comprehension | 2 |
| 10 | cost-control comprehension | 2 |
| 11 | risk discovery | 2 |
| 12 | extension safety | 2 |
| 13 | approval awareness | 2 |
| 14 | limitation honesty | 2 |
| 15 | independence | 2 |
| | **total** | **29/30** |

**Result: PASS.** ≥25/30; no 0 in architecture/validation/evidence/risk; 0 human
interventions; no hidden command supplied. The single point lost (validation
friction) was fixed at root cause (venv step added to `START_HERE` §6 and other
setup blocks).

## Minimum acceptance

- No category scored `0` for **architecture (2), validation (5), evidence (6),
  or risk (11)**.
- Total ≥ **25/30**.
- No more than **two** human interventions.
- No hidden command supplied by the implementation agent.

## Recorded per run

Time to first successful validation, misunderstood terms, missing documentation,
incorrect assumptions, human interventions, and the files changed because of the
test. After fixing defects, rerun the affected portions with a fresh tester
context where possible.
