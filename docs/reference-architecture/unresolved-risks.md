# Unresolved Risks

**Status:** CURRENT · **Audience:** all. Machine-readable copy:
[`governance/unresolved_risks.yml`](../../governance/unresolved_risks.yml).
Medium and high risks are listed honestly — none is hidden to make the capstone
look cleaner. Blocked work is shown as BLOCKED, never as complete.

| id | title | sev | status | approval | next action |
| --- | --- | --- | --- | --- | --- |
| RISK-01 | Sprint 7 live IAM reduction not executed | MEDIUM | BLOCKED | `ATLAS_APPROVE_IAM` | apply scoped reduction on `atlas-github-integration` dataEditor |
| RISK-02 | Sprint 7 positive/negative IAM tests not executed | MEDIUM | BLOCKED | `ATLAS_APPROVE_IAM` | run authorized + denied ops, record both |
| RISK-03 | Billed BigQuery performance suite not executed | LOW | BLOCKED | `ATLAS_APPROVE_PERFORMANCE_TESTS` + byte ceiling | execute once, record billed bytes/slot/correctness |
| RISK-04 | Live retention/expiration application not executed | LOW | BLOCKED | `ATLAS_APPROVE_RETENTION_MUTATION` | apply TTL to temporary resources only, verify |
| RISK-05 | Composer customer-project task-log limitation | LOW | MITIGATED | — | direct Cloud Logging export at create time |
| RISK-06 | Synthetic 50k-row scale | MEDIUM | ACCEPTED | — | do not claim production-scale perf/cost |
| RISK-07 | No multi-environment production promotion | MEDIUM | ACCEPTED | — | future sprint scope |
| RISK-08 | No streaming/event-driven/CDC ingestion | LOW | ACCEPTED | — | future capstone (prefer API/event) |
| RISK-09 | External consumers not discoverable from repository | MEDIUM | ACCEPTED | — | only internal consumers registered |
| RISK-10 | Public extraction not yet performed | MEDIUM | OPEN | `ATLAS_APPROVE_PUBLIC_EXTRACTION` | run `validate_public_extraction.py`; Sprint 8+ extraction |
| RISK-12 | No second-project generation test | MEDIUM | DEFERRED | — | post-Atlas template validation |
| RISK-13 | Clean-clone platform limitations | LOW | OPEN | — | see [clean-clone-results.md](../evidence-sprint8/clean-clone-results.md) |
| RISK-14 | Independent handoff ambiguity | LOW | OPEN | — | see [independent-handoff-results.md](../evidence-sprint8/independent-handoff-results.md) |

## Sprint 7 blocked-gate disposition

At Sprint 8 preflight the IAM, performance, and retention approval variables were
**absent**. Per the master prompt's missing-approval behavior, these gates:

- remain **BLOCKED** (RISK-01..04),
- retain their exact execution plans (in
  [iam-review-sprint7.md](../iam-review-sprint7.md),
  [performance-review-sprint7.md](../performance-review-sprint7.md),
  [retention-policy-sprint7.md](../retention-policy-sprint7.md)),
- are **not** re-run and **not** weakened,
- do **not** contribute any "complete" claim.

If the approvals are provided later, execute only after the reference package and
clean-clone path are stable, following the IAM/performance/retention legs
described in the Sprint 8 prompt Phase 13. These are optional closure
improvements, not automatic requirements for Sprint 8 completion.
