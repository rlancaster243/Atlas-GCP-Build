# Operator Onboarding

**Status:** CURRENT · **Audience:** operator. Three modes, from safe review to
controlled operation. Start at [`../../START_HERE.md`](../../START_HERE.md).

## Mode 1 — Credentialless review (no GCP access)

Safe anywhere. Inspect architecture, run static validation, inspect governance,
lineage, evidence, and release history.

```bash
cd Atlas-GCP-Build
python3 -m venv .venv && source .venv/bin/activate   # required on PEP 668 hosts
pip install -r requirements.txt -r requirements-ci.txt
export PYTHONPATH=src                            # atlas.* modules live under src/
bash scripts/validate_ci.sh --mode static        # 21 gates, no credentials
python -m atlas.governance.catalog check         # governance + drift
python -m atlas.governance.lineage               # lineage graph
python -m atlas.reference.validate               # reference package + evidence
```

Read: [architecture-overview](../reference-architecture/architecture-overview.md),
[evidence-index](../reference-architecture/evidence-index.md), release table in
[README.md](../../README.md).

## Mode 2 — Read-only GCP verification

Requires `ATLAS_APPROVE_HANDOFF_LIVE_READ=true`. **No mutation.**

- Verify active project: `gcloud config get-value project` (expect `example-gcp-project`).
- Inspect datasets: `bq ls`; selected schemas: `bq show --schema <dataset>.<table>`.
- Inspect operational audit: query `atlas_ops.pipeline_runs` / `deployments`.
- Inspect latest deployment evidence and observability resources
  (`gcloud monitoring`, `gcloud logging`), Composer state
  (`gcloud composer environments list`).
- BigQuery **dry runs** only (`--dry_run` or `cost_guard estimate`). Never create
  resources, never run billed queries, never create Composer.

## Mode 3 — Controlled operation

Every mutation is gated on an `ATLAS_APPROVE_*` variable. Use the existing
runbooks:

- Deploy / rollback → [ci-cd-runbook-sprint4.md](../ci-cd-runbook-sprint4.md)
- Observability / per-alert → [observability-runbook-sprint5.md](../observability-runbook-sprint5.md)
- Recovery → [recovery-runbook-sprint6.md](../recovery-runbook-sprint6.md)
- Governance procedures → [governance-model-sprint7.md](../governance-model-sprint7.md)
- Cost controls → [cost-review-sprint7.md](../cost-review-sprint7.md)
- Approval variables → [agent-onboarding.md](agent-onboarding.md)

Use the [operator checklist](operator-checklist.md) for each run and the
[first-hour guide](operator-first-hour.md) when you are brand new.
