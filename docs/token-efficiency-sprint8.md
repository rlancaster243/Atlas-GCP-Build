# Atlas Sprint 8 Token & Compute Efficiency

Target: **50–65% of Sprint 7 agent consumption**. Sprint 8 is documentation and
validation heavy, not implementation heavy: it curates existing evidence rather
than building new platforms. Exact token telemetry is not exposed to the agent;
proxies are tracked and updated at closeout.

## Efficiency strategy

1. One comprehensive Phase-0 scan (done) → preflight + this context pack; targeted
   reads afterward.
2. **Link, don't duplicate** — the reference package points to Sprint 1–7 docs,
   ADRs, tests, and validation reports instead of re-prosing them.
3. One navigational reference package; one focused handoff CI gate
   (`gate_reference_handoff`) — not many unrelated gates.
4. Fresh directories for clean-clone reproduction; one independent handoff
   subagent (only repo + START_HERE + assignment).
5. No Composer, no billed BigQuery, no IAM/retention mutation unless the
   corresponding approval variable is present.
6. Reuse existing diagrams/text-diagrams; regenerate only if materially wrong.
7. Record human interventions during handoff testing honestly.

## Proxy ledger (updated through the sprint)

| Proxy | Sprint 7 (reference) | Sprint 8 (actual) |
| --- | --- | --- |
| Full repository scans | 1 | 1 (Phase 0) + targeted reads |
| Composer create/delete cycles | 0 | **0** |
| Live deployment cycles | 0 | **0** |
| Billed BigQuery workloads | 0 (dry-run only) | **0** |
| Live GCP windows | 1 bounded read-only/dry-run | **0** (no approvals set) |
| New CI gates added | 5 | **1** (`gate_reference_handoff`) |
| Independent handoff runs | — | 1 (scored 29/30) |
| Clean-clone attempts | — | 2 (attempt 1 found defect, attempt 2 PASS) |
| Failed onboarding steps repaired | — | 2 (PYTHONPATH=src; PEP 668 venv) |
| Major plan regenerations | 0 | **0** |
| Human correction events | 0 | 0 (tester self-resolved friction) |

Model: Opus 4.8. Harness: Cursor Cloud Agent. Cloud operations: 0 mutating,
0 billed. Composer cycles: 0. The envelope target (50–65% of Sprint 7) was met:
Sprint 8 was documentation/validation work with no cloud provisioning, one new
gate, and a single independent handoff subagent.

## Scope-compression tripwire

If projected work approaches **75% of Sprint 7** consumption, stop and propose
compression: e.g., collapse the five operating/security/reliability/observability/
cost model docs into fewer files that link harder to existing runbooks; reduce
the handoff to the single highest-value independent assignment; defer the
optional read-only GCP leg. Recorded here if triggered.
