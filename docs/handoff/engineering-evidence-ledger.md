# Engineering Evidence Ledger

**Status:** CURRENT · **Audience:** reviewer, interviewer. Detailed companion to
[capability-evidence-map](../reference-architecture/capability-evidence-map.md).
Maps concrete Atlas artifacts to competency domains. Framing is honest: this is
evidence of capability at synthetic scale, not a seniority claim.

| Domain | Concrete evidence in repo | Level | Limitation |
| --- | --- | --- | --- |
| SQL & warehousing | `dbt/atlas_dbt/models` (grain, dedup, incremental, partition pruning); `performance-review-sprint7.md` | Demonstrated | synthetic 50k rows |
| dbt | sources/staging/intermediate/core/marts + tests + contracts + `schema_check` | Demonstrated | single project |
| GCP | Sprints 1–7 live: GCS, BigQuery, WIF, Composer, Logging, Monitoring | Demonstrated | ephemeral env; 1 blocked IAM reduction |
| Pipeline engineering | `src/atlas/{ingestion,batch,ops}`, retries/backfills, verified recovery | Demonstrated | batch only |
| Software engineering | 21-gate `validate_ci.sh`, 269-test unit+Airflow gate (282 all suites), immutable bundles, rollback | Demonstrated | single repo |
| Governance & security | `src/atlas/governance/*`, `governance/*`, ADR-016–019 | Demonstrated | least privilege not proven live (RISK-01/02) |
| Operations | Sprints 5/6 alerts, runbooks, incident reports, recovery audit | Demonstrated | representative live subset |
| Reproducibility (Sprint 8) | `validate_clean_clone.sh`, reference package, evidence index | Demonstrated | single tester context |

## Next-level requirements (honest)

- **Scale:** rerun performance/cost at production volume with billed metrics
  (RISK-03, requires `ATLAS_APPROVE_PERFORMANCE_TESTS`).
- **Least privilege:** execute the IAM reduction + negative test (RISK-01/02,
  requires `ATLAS_APPROVE_IAM`).
- **Promotion:** multi-environment production promotion (RISK-07).
- **Ingestion:** streaming/event-driven/API sources (RISK-08; extension plan in
  [extension-points](../reference-architecture/extension-points.md)).
- **Template:** extract + validate via a separate project (RISK-11/12).

No claim of enterprise governance, regulatory certification, production-scale
performance, or senior tenure is made.
