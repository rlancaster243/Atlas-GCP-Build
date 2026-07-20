# Agent Task Protocol

**Status:** CURRENT · **Audience:** coding agent. The required sequence for any
change. This protocol never tells you to ask the original builder what the
repository means — the answer is always in the repository (see the
[source-of-truth hierarchy](agent-onboarding.md#source-of-truth-hierarchy)).

## Before implementation

1. Inspect current `main` (`git fetch`, `git log`, tags).
2. Read [`../../START_HERE.md`](../../START_HERE.md).
3. Read [architecture-invariants](../reference-architecture/architecture-invariants.md).
4. Identify affected components ([reusable](../reference-architecture/component-catalog-reusable.md) / [Atlas-specific](../reference-architecture/component-catalog-atlas-specific.md)).
5. Identify owners and consumers (`governance/consumers.yml`, `impact`).
6. State the intended change.
7. List affected files.
8. State risks.
9. Define tests.
10. Define rollback / reversal.
11. Identify required approvals (`ATLAS_APPROVE_*`).

## After implementation

1. Run focused tests.
2. Run canonical static CI (`bash scripts/validate_ci.sh --mode static`).
3. Update evidence ([evidence index](../reference-architecture/evidence-index.md)).
4. Update governance metadata (dbt `meta.governance` / `governance/*.yml`).
5. Update lineage if affected (`PYTHONPATH=src python -m atlas.governance.lineage`).
6. Update consumer impact (`PYTHONPATH=src python -m atlas.governance.impact --asset <id>`).
7. Update ADRs when a decision changes.
8. Confirm no invariant was silently broken.
9. Produce an honest limitations section (live vs static vs blocked).

## Change plan template

```
Intended change:
Affected files:
Invariants touched (and how preserved):
Tests (new/updated):
Rollback:
Approvals required:
Evidence + status (live/static/blocked):
Honest limitations:
```

Use [extension-points](../reference-architecture/extension-points.md) for the
common unsafe shortcut to avoid per extension type.
