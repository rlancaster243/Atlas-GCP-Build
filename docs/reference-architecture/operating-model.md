# Operating Model

**Status:** CURRENT · **Audience:** operator, reviewer. Who does what, with which
authority, and where the procedure lives. Detail is in the runbooks; this is the
ownership map.

| Responsibility | Owner | Authority / gate | Procedure |
| --- | --- | --- | --- |
| Ownership of assets | technical owners in `governance/*` + dbt `meta` | governance CI | [governance-model-sprint7.md](../governance-model-sprint7.md) |
| Routine validation | any engineer / agent | none (credentialless) | `validate_ci.sh --mode static` |
| Deployment authority | operator | `ATLAS_APPROVE_DEPLOY` + WIF | [ci-cd-runbook-sprint4.md](../ci-cd-runbook-sprint4.md) |
| Incident authority | operator (on-call) | — | [observability-runbook-sprint5.md](../observability-runbook-sprint5.md), [on-call-model-sprint5.md](../on-call-model-sprint5.md) |
| Data-quality review | data owner | quality gate blocks publish | dbt tests + `quality_results` |
| Recovery approval | operator | verification required (INV-O3) | [recovery-runbook-sprint6.md](../recovery-runbook-sprint6.md) |
| Release management | release owner | `ATLAS_APPROVE_RELEASE` | tag on validated merge SHA |
| Evidence preservation | all | teardown allow-list (INV-O7) | validation reports + `docs/evidence-sprint*/` |
| Teardown | operator | `ATLAS_APPROVE_TEARDOWN` | [manage_atlas_composer.sh](../../scripts/manage_atlas_composer.sh) |
| Change review | reviewer + CI | P0/P1 gate | [agent-task-protocol.md](../handoff/agent-task-protocol.md) |

## Cadence

- Every change: credentialless CI must pass; invariants confirmed.
- Every deployment: immutable bundle → migrations → smoke → success/rollback.
- Every incident: detect → contain → diagnose → recover → verify → prevent, with
  durable audit and an incident report.
- Every release: green CI on merged main → annotated tag on the exact SHA →
  docs-only release-row follow-up.

New operators start with [operator-onboarding.md](../handoff/operator-onboarding.md)
and the [operator-first-hour.md](../handoff/operator-first-hour.md) checklist.
