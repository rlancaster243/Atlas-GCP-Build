# Agent Onboarding

**Status:** CURRENT · **Audience:** coding agent. Everything a coding agent needs
to work on Atlas **without asking the original builder what the repository
means.** Start at [`../../START_HERE.md`](../../START_HERE.md).

## Canonical starting document

[`../../START_HERE.md`](../../START_HERE.md), then this file and the
[agent task protocol](agent-task-protocol.md).

## Repository scope & protected paths

In scope: `` ELT platform. **Do not modify** (separate lifecycle):
Document any unavoidable exception.

## Source-of-truth hierarchy

1. Code + config (behavior). 2. dbt `meta.governance` (model governance).
3. `governance/*.yml` (non-dbt governance + policy). 4. ADRs (decisions).
5. `validation-report-sprint{1..7}.md` (evidence). 6. Reference package (map).

## Architecture invariants

Read and preserve [architecture-invariants](../reference-architecture/architecture-invariants.md).
Breaking one silently is a P0.

## CI contract (credentialless)

```bash
bash scripts/validate_ci.sh --mode static           # all gates
bash scripts/validate_ci.sh --mode static --group python   # one slice
# direct module commands need the src path (no installed package):
export PYTHONPATH=src
python -m atlas.governance.lineage
python -m atlas.governance.impact --asset fct_events
python -m atlas.reference.validate
```
PR CI is credentialless (INV-L1). Cloud validation lives in trusted workflows.
Do not duplicate validation logic in workflow YAML.

## Approval variables (missing = do safe work, record blocked, never fake)

`ATLAS_APPROVE_PROVISION, _IAM, _SCHEMA_MUTATION, _RETENTION_MUTATION,
_PERFORMANCE_TESTS, _LIVE_ACCEPTANCE, _COMPOSER_CREATE, _TEARDOWN,
_HANDOFF_LIVE_READ, _PUBLIC_EXTRACTION, _RELEASE`. Missing approval → complete the
static work, record the blocked gate, preserve the plan, do not weaken the
control, do not claim live proof.

## Conventions

- Branches: `cursor/<descriptive-name>-<suffix>`; never move Sprint tags.
- Focused commits; buildable repository after each commit.
- New ADR only for a real decision; amend an existing ADR when appropriate.
- Every asset needs `meta.governance` (models) or a `governance/` entry (non-dbt).
- Update the [evidence index](../reference-architecture/evidence-index.md) and
  lineage when affected.

## Evidence & test expectations

Add/adjust tests for every change (269-test unit+Airflow gate; 282 across all
suites). Governance, schema, lineage,
security, and cost gates must stay green. Record evidence with the correct
live/static/blocked status; never mark blocked work complete.

## Prohibited claims

Do not claim production scale, enterprise/regulatory compliance, complete least
privilege without live negative-test evidence, reusable-template status,
second-project validation, or public-repository readiness. See
[capability-evidence-map](../reference-architecture/capability-evidence-map.md).

## Final report expectations

State intended change, invariants touched, tests, rollback, approvals, and an
honest limitations section (see [agent-task-protocol](agent-task-protocol.md)).
