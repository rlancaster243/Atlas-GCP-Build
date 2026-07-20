# Atlas Demo Script

**Status:** CURRENT · A bounded, safe (credentialless) demo sequence. Every step
runs without GCP access and finishes in a few minutes.

```bash
cd Atlas-GCP-Build
python3 -m venv .venv && source .venv/bin/activate   # required on PEP 668 hosts
pip install -r requirements.txt -r requirements-ci.txt
export PYTHONPATH=src            # atlas.* modules live under src/
```

1. **Starting point** — open [`../../START_HERE.md`](../../START_HERE.md); show the
   four audience paths.
2. **Architecture** — open [architecture-overview](../reference-architecture/architecture-overview.md); walk the four flows.
3. **Static validation** — `bash scripts/validate_ci.sh --mode static` → green
   gate summary (`validate_ci: PASS`).
4. **Governance catalog** — `python -m atlas.governance.catalog check` →
   "governance catalog matches sources" (22 assets).
5. **Lineage** — `python -m atlas.governance.lineage` → 26 nodes / 29 edges.
6. **Schema compatibility** — show `governance/schemas/manifests/baseline.json`
   and `sql/migrations/checksums.lock`; explain the immutability gate.
7. **Cost guard** — `python -m atlas.observability.cost_guard check-partition-filter
   --sql-file observability/performance/queries/unbounded_scan.sql --asset atlas_raw.events`
   → BLOCKED before spend ($0).
8. **Evidence index** — `python -m atlas.reference.validate` → OK; open
   [evidence-index](../reference-architecture/evidence-index.md).
9. **Incident & recovery** — open `docs/incident-report-INC-S6-001-batch-contamination.md`
   and `docs/validation-report-sprint6.md` §recovery.
10. **Unresolved risks** — open [unresolved-risks](../reference-architecture/unresolved-risks.md);
    call out the three BLOCKED gates honestly.

No mutation, no billed query, no Composer. The whole demo is credentialless and
reproducible.
