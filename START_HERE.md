# Start Here

Atlas is a production-data-platform template, not a one-command production
service. Begin with the route matching your responsibility.

## Adopter / platform engineer

1. Read `README.md` and `docs/template-configuration.md`.
2. Review `docs/reference-architecture/architecture-invariants.md`.
3. Replace all sample environment values.
4. Run `bash scripts/validate_ci.sh --mode static`.
5. Exercise the local pipeline and tests.
6. Provision an isolated GCP namespace using plan mode first.
7. Run one batch, one deliberate failure, one recovery, and cleanup.
8. Record environment-specific evidence instead of inheriting the reference
   implementation's claims.

## Operator

Read:

- `docs/handoff/operator-onboarding.md`
- `docs/runbook.md`
- `docs/runbook-sprint3.md`
- `docs/observability-runbook-sprint5.md`
- `docs/recovery-runbook-sprint6.md`

Be able to answer: Did the pipeline run? Is the data correct and complete? Who is
alerted? How is it recovered? How is recurrence prevented?

## Reviewer / architect

Start with:

- `docs/reference-architecture/README.md`
- `docs/reference-architecture/system-context.md`
- `docs/reference-architecture/interfaces-and-contracts.md`
- `docs/reference-architecture/security-and-identity-model.md`
- `docs/reference-architecture/reliability-and-recovery-model.md`
- `docs/reference-architecture/unresolved-risks.md`

## Coding agent

Read `docs/handoff/agent-onboarding.md`. Treat generated code as provisional.
State assumptions, risks, affected files, test plan, and rollback considerations
before major changes. Do not claim production readiness without environment-specific
evidence.

## Credentialless verification

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-ci.txt
export PYTHONPATH=src
bash scripts/validate_ci.sh --mode static
```
