# Evidence Index

**Status:** CURRENT · **Audience:** reviewer, agent. Human-readable view of the
machine-readable claim ledger
[`governance/generated/evidence-index.json`](../../governance/generated/evidence-index.json),
validated by `python -m atlas.reference.validate`. Every major claim maps to a
path + evidence type + live/static/blocked status. The validator fails if an
evidence path is missing, a claim id is duplicated, a LIVE claim has only
documentation evidence, a blocked claim is presented as complete, or a
verification commit is absent.

## How to reproduce

```bash
export PYTHONPATH=src                          # atlas.* modules live under src/
python -m atlas.reference.validate             # manifest + evidence index
bash scripts/validate_ci.sh --mode static      # includes gate_reference_handoff
```

## Claim summary (30 claims)

| status | count | claims |
| --- | --- | --- |
| PROVEN_LIVE | 8 | ingest/load, WIF, release, alerting drill, incident, recovery, quality gate |
| PROVEN_STATIC | 7 | CI, rollback ADR, logging, monitoring, lineage, governance SoT, cost block |
| PROVEN_TEST | 8 | generation, dbt, orchestration, retries, schema check, migration immutability, impact, security, retention |
| DRY_RUN | (within static) | performance baseline, cost block |
| PLANNED | 2 | clean-clone (CLM-26), independent handoff (CLM-27) — recorded after runs |
| BLOCKED | 3 | live IAM (CLM-28), billed perf (CLM-29), live retention (CLM-30) |

## Live vs static (must stay separated)

- **Proven live** (real cloud runs recorded in validation/incident reports):
  immutable ingest, BigQuery load, WIF deploy, immutable release, alerting drill,
  incident diagnosis, verified recovery, quality-gate block.
- **Proven static / by tests** (offline gates + 269-test unit+Airflow gate,
  240 unit / 29 Airflow, plus dbt tests):
  generation determinism, dbt transforms, orchestration, schema compatibility,
  migration immutability, lineage/impact, governance source-of-truth, security
  scanners, retention validation.
- **Dry-run ($0):** performance baseline, cost-guard block.
- **Blocked (not executed):** live IAM reduction + tests, billed performance
  suite, live retention application — see [unresolved-risks.md](unresolved-risks.md).

The evidence index deliberately does **not** upgrade any dry-run or static claim
to "live", and never marks a blocked claim complete.
