# Atlas Question Bank

**Status:** CURRENT · Credible, evidence-bound answers to likely reviewer
questions. Each links to the authoritative source.

- **Why batch instead of streaming?** The engineering problem is correctness,
  governance, and recovery at controlled cost; batch makes idempotency, replay,
  and reconciliation tractable and cheap. Streaming is a deliberate non-goal
  (RISK-08). → [system-context](../reference-architecture/system-context.md).
- **Why BigQuery?** Serverless, partitioning/clustering, dry-run cost estimation,
  `INFORMATION_SCHEMA.JOBS` for cost/perf evidence. → [cost model](../reference-architecture/cost-and-lifecycle-model.md).
- **Why dbt?** Declarative models, tests, contracts, lineage, and schema-evolution
  hooks. → `dbt/atlas_dbt`, ADR-016/017.
- **Why Composer?** Managed Airflow parity with production orchestration without
  running our own control plane. → ADR-005.
- **Why ephemeral Composer?** Cost control + drift avoidance; created for
  acceptance, torn down while preserving durable evidence (INV-L7/O7). → ADR-010.
- **How is idempotency achieved?** Stable `batch_id`, create-only loads, dbt
  incremental `unique_key`, global fact uniqueness (INV-D2/D3/D5). → ADR-006.
- **How are duplicates classified?** Within-batch duplicate vs cross-batch replay
  are distinct scopes in `int_event_classification` (INV-D4). → ADR-006 amendment.
- **How are schema changes controlled?** Classified COMPATIBLE/CONDITIONAL/
  BREAKING/PROHIBITED; migrations immutable via checksum lock; breaking needs
  impact evidence (INV-D8/G4/G5). → ADR-017.
- **How is rollback protected?** Schema-compatibility checked before rollback;
  failed deploys never publish success (INV-L5/L6). → ADR-015.
- **What happens when data quality fails?** Publication is blocked; quality
  results recorded; alert + runbook (INV-D7). → `game-day-results-sprint6`.
- **How are incidents detected?** Retries, dbt tests, guards, telemetry → alerts
  mapped to runbooks (INV-O6). → `observability-runbook-sprint5`.
- **How is recovery verified?** SUCCESS gated on `VERIFIED` in `recovery_actions`
  (INV-O3). → INC-S6-001.
- **What is genuinely production-ready?** The controls and evidence discipline:
  credentialless CI, keyless deploy, immutable releases, governance gates,
  observability, verified recovery.
- **What remains unproven?** Production-scale performance/cost, live least
  privilege, live retention, multi-env promotion, streaming, template reuse. →
  [unresolved-risks](../reference-architecture/unresolved-risks.md).
- **What would change at larger scale?** Slot management, incremental strategies,
  partition/cluster tuning, real SLOs/alert thresholds, multi-env promotion.
- **What would be extracted into a template?** RC-01..22; the plan and acceptance
  (not executed in Sprint 8).
