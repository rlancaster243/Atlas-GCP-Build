# System Context

**Status:** CURRENT · **Audience:** all · **Source of truth:** code + ADRs.
This is a curated map; it links to authoritative sources rather than copying them.

## Problem modeled

Atlas models a **batch analytics platform for a synthetic event stream** (users
performing actions across countries). The engineering problem — not the business
domain — is the point: prove correct, governed, observable, recoverable batch
data processing on GCP with reproducible evidence. Scale is deliberately modest
(~50,000 events/batch); Atlas is production-*oriented*, not production-*scale*.

## Context diagram

```
                          ┌───────────────────────── Google Cloud (example-gcp-project) ─────────────────────────┐
  ┌─────────────┐         │                                                                                        │
  │ Human        │ approves│  ┌────────────┐   ┌───────────┐   ┌───────────────────────────┐   ┌────────────────┐ │
  │ operator     ├────────►│  │ Cloud       │   │ BigQuery   │   │ Cloud Composer (Airflow    │   │ Cloud Logging  │ │
  │ (the primary operator)    │         │  │ Storage     │──►│ raw +      │──►│ 3.1.7) — atlas_batch and   │──►│ + Monitoring   │ │
  └─────┬───────┘         │  │ (immutable  │   │ dbt models │   │ observability DAGs         │   │ (metrics,      │ │
        │                 │  │  landing +  │   │ (staging→  │   └───────────────────────────┘   │  alerts, dash) │ │
        │ runs            │  │  releases)  │   │  marts)    │            │                        └────────────────┘ │
  ┌─────▼───────┐         │  └────────────┘   └───────────┘            │ audit                                       │
  │ Coding agent │ CI/CD  │        ▲                 ▲                  ▼                                             │
  │ (Cursor)     ├────────┼────────┼─────────────────┼──────► atlas_ops.* operational tables                        │
  └─────┬───────┘         │        │ WIF (keyless)   │                                                              │
        │                 └────────┼─────────────────┼──────────────────────────────────────────────────────────────┘
        │ pull request             │                 │
  ┌─────▼───────────────┐   ┌──────┴───────┐   ┌──────┴───────┐
  │ GitHub (CI/CD:      │──►│ Synthetic     │   │ dbt          │
  │ credentialless PR,  │   │ event         │   │ (BigQuery    │
  │ trusted deploy)     │   │ generator     │   │  adapter)    │
  └─────────────────────┘   └──────────────┘   └──────────────┘
```

## Building blocks (where each lives)

| Block | Purpose | Source |
| --- | --- | --- |
| Synthetic event source | Deterministic 50k-event generation with seeded anomalies | `src/atlas/generator`, `scripts/generate_events.py`, `config/anomaly_profile.yaml` |
| Batch ingestion | Immutable JSONL → run-scoped GCS paths | `src/atlas/ingestion`, `scripts/upload_events.py` |
| Cloud Storage landing | Immutable raw artifacts + release bundles | GCS buckets (see `infra/`) |
| BigQuery raw | Partitioned/clustered raw table | `sql/`, `src/atlas/loader` |
| dbt transformation | staging → classification → accepted/rejected → core (fact/dims) → marts | `dbt/atlas_dbt` |
| Airflow orchestration | `atlas_batch_pipeline`, `atlas_observability_monitor` | `dags/`, `src/atlas/batch` |
| CI/CD | Credentialless PR CI + trusted WIF deploy + rollback | `scripts/validate_ci.sh`, `.github/workflows/`, ADR-008/009/010 |
| Composer deployment | Ephemeral managed Airflow for acceptance | `scripts/manage_atlas_composer.sh`, ADR-005/010 |
| Observability | Structured logs, metrics, alerts, dashboard | `src/atlas/observability`, `observability/`, ADR-011 |
| Recovery | Recovery-action audit + verification | `src/atlas/ops`, `docs/recovery-runbook-sprint6.md`, ADR-014 |
| Governance | Contracts, schema compat, lineage, retention | `src/atlas/governance`, `governance/`, ADR-016–019 |
| Security | Keyless WIF, least-privilege review, scanners | `src/atlas/governance/security_policy.py`, ADR-009/018 |
| Cost controls | Config-driven ceilings + dry-run guard | `config/cost_controls.yaml`, `src/atlas/observability/cost_guard.py`, ADR-020 |

## Actors and interactions

- **Human operator** — approves gated mutations (`ATLAS_APPROVE_*`), owns
  incident/recovery/release authority ([operating model](operating-model.md)).
- **Coding agent** — implements changes via the [agent task protocol](../handoff/agent-task-protocol.md); bound by invariants and CI.
- **GitHub** — runs credentialless PR CI; trusted workflows authenticate to GCP via WIF (no keys).
- **Consumers** — internal only, registered in `governance/consumers.yml` (dashboard, monitor, reconciliation, alerting, analytics readers). External consumer discovery is out of repository scope (a known limitation).

## System boundaries and external dependencies

In scope: the `` ELT platform. Out of scope (separate lifecycle):
External dependencies: Google Cloud (BigQuery, GCS, Composer, Logging,
Monitoring, IAM/WIF), GitHub Actions, dbt (BigQuery adapter), Apache Airflow
3.1.7. No streaming, Pub/Sub, Dataflow, CDC, or ML dependencies.

See [architecture-overview.md](architecture-overview.md) for the data/control/
operational/governance flows.
