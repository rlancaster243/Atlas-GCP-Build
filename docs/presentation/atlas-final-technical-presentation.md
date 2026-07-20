# Atlas — Final Technical Presentation (source)

**Status:** CURRENT · Source for ~12–15 slides. No slide deck binary is created.
Each slide: purpose, key points, proposed visual, evidence source, speaker notes,
likely reviewer question. Evidence links resolve to repository artifacts.

---

### Slide 1 — Problem & objective
- **Purpose:** frame the engineering problem. **Key points:** correct, governed,
  observable, recoverable batch data platform on GCP; synthetic scale by design.
- **Visual:** one-line value statement. **Evidence:** [system-context](../reference-architecture/system-context.md).
- **Notes:** production-*oriented*, not production-*scale*. **Q:** why batch?

### Slide 2 — Architecture overview
- **Key points:** four flows (data/control/operational/governance).
- **Visual:** the context diagram. **Evidence:** [architecture-overview](../reference-architecture/architecture-overview.md). **Q:** where are the boundaries?

### Slide 3 — Data lifecycle
- **Key points:** generate → GCS → raw → dbt → marts; immutable, run-scoped.
- **Visual:** data-flow arrows. **Evidence:** `validation-report-sprint1/2`. **Q:** how is idempotency achieved?

### Slide 4 — Warehouse & dbt model
- **Key points:** staging→classification→accepted/rejected→fact/dims→marts;
  contracts + tests. **Visual:** dbt DAG. **Evidence:** `dbt/atlas_dbt`. **Q:** why dbt?

### Slide 5 — Orchestration & identity
- **Key points:** Airflow; `batch_id` vs `pipeline_run_id`; retries/backfills.
- **Evidence:** `validation-report-sprint3`, ADR-006. **Q:** exact-rerun idempotency?

### Slide 6 — CI/CD & secure deployment
- **Key points:** credentialless PR CI; keyless WIF; immutable releases; rollback.
- **Evidence:** ADR-008/009/010, `ci-cd-runbook-sprint4`. **Q:** why keyless?

### Slide 7 — Observability
- **Key points:** structured logs, correlation ids, metrics, alerts→runbooks.
- **Evidence:** ADR-011, `observability-runbook-sprint5`. **Q:** NO_DATA alerts?

### Slide 8 — Failure & recovery
- **Key points:** detect→contain→diagnose→recover→verify→prevent; verified repair.
- **Evidence:** `game-day-results-sprint6`, INC-S6-001. **Q:** how is recovery verified?

### Slide 9 — Governance & schema evolution
- **Key points:** one source of truth; compatibility classes; migration immutability.
- **Evidence:** ADR-016/017, `governance/`. **Q:** how are breaking changes blocked?

### Slide 10 — Security & IAM
- **Key points:** WIF, no keys/Owner/Editor; one blocked least-privilege reduction.
- **Evidence:** [security model](../reference-architecture/security-and-identity-model.md). **Q:** is least privilege proven?

### Slide 11 — Performance & cost
- **Key points:** dry-run baseline, partition pruning, cost-guard $0 block.
- **Evidence:** `performance/cost-review-sprint7`. **Q:** what about production scale?

### Slide 12 — Incidents & lessons
- **Key points:** INC-S6-001/002; the same-date reprocessing fix (ADR-006 amend).
- **Evidence:** incident reports. **Q:** what recurred and how was it prevented?

### Slide 13 — Evidence & reproducibility
- **Key points:** evidence index; clean-clone; independent handoff.
- **Evidence:** [evidence-index](../reference-architecture/evidence-index.md), `evidence-sprint8/`. **Q:** can someone else run it?

### Slide 14 — Limitations
- **Key points:** synthetic scale; blocked IAM/perf/retention; no streaming; not a template.
- **Evidence:** [unresolved-risks](../reference-architecture/unresolved-risks.md). **Q:** what is NOT production-ready?

### Slide 15 — Future extensions
- **Key points:** API ingestion, template extraction + second-project validation.
