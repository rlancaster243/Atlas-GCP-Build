# Independent Handoff Assignment

**Status:** CURRENT · **Audience:** independent tester (engineer or coding agent).
You receive **only**: the repository clone, [`../../START_HERE.md`](../../START_HERE.md),
and this assignment. You do **not** receive prior conversations, the
implementation agent's reasoning, hidden commands, or verbal help. Record where
you struggle — that feedback repairs the handoff.

## Assignment (complete in order)

1. Explain Atlas in your own words (2–4 sentences).
2. Identify the data grain of the fact table.
3. Explain the difference between `batch_id` and `pipeline_run_id`.
4. Locate the current release (tag + commit).
5. Run credentialless validation and report the result.
6. Locate evidence for **one successful deployment**.
7. Locate evidence for **one failed deployment**.
8. Locate evidence for **one recovery**.
9. Explain how schema changes are controlled.
10. Explain how an unsafe/unbounded query is blocked.
11. Identify all unresolved **high-priority** risks.
12. Propose how to add an **API ingestion source**.
13. List the files and invariants affected by that extension.
14. Identify what requires explicit approval.
15. State which claims are **not** proven at production scale.

## Allowed inputs only

- `START_HERE.md` and whatever it links to inside the repository.
- The credentialless command in START_HERE §6.
- No GCP credentials required. No outside help on the first attempt.

## What we measure

Time to first successful validation, misunderstood terms, missing documentation,
incorrect assumptions, and any human intervention. Results and the score go in
[handoff-scorecard.md](handoff-scorecard.md) and
[../evidence-sprint8/independent-handoff-results.md](../evidence-sprint8/independent-handoff-results.md).

## Hints are NOT provided

If a step cannot be completed from the repository alone, that is a **handoff
defect** to be fixed in documentation/scripts — not something to be coached
around. Report it verbatim.
