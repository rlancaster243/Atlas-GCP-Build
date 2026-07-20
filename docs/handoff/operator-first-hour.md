# Operator First Hour

**Status:** CURRENT · **Audience:** new operator. A bounded, safe first session
that needs no GCP credentials.

1. **Orient (10 min).** Read [`../../START_HERE.md`](../../START_HERE.md) and
   [system-context](../reference-architecture/system-context.md).
2. **Validate locally (15 min).**
   ```bash
   cd Atlas-GCP-Build
   python3 -m venv .venv && source .venv/bin/activate   # required on PEP 668 hosts
   pip install -r requirements.txt -r requirements-ci.txt
   bash scripts/validate_ci.sh --mode static
   ```
   Expect a green gate summary (`validate_ci: PASS`). This proves your
   environment and the repository without touching GCP.
3. **Inspect governance & lineage (10 min).**
   ```bash
   export PYTHONPATH=src            # atlas.* modules live under src/
   python -m atlas.governance.catalog check
   python -m atlas.governance.lineage
   python -m atlas.reference.validate
   ```
4. **Read the operating model (10 min).**
   [operating-model](../reference-architecture/operating-model.md) — know who has
   deployment, incident, recovery, and release authority.
5. **Skim the risks (10 min).**
   [unresolved-risks](../reference-architecture/unresolved-risks.md) — note the
   three BLOCKED Sprint 7 gates and that they require approval variables.
6. **Know the "never casually" list (5 min).** START_HERE §14.

After the first hour you can safely review, validate, and (with
`ATLAS_APPROVE_HANDOFF_LIVE_READ=true`) inspect the live project read-only. Do
not perform any mutation until you have read the relevant runbook and have the
matching `ATLAS_APPROVE_*` approval.
