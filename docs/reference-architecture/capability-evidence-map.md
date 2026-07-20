# Capability & Evidence Map

**Status:** CURRENT · **Audience:** reviewer, interviewer. Maps Atlas evidence to
engineering competency domains. Each capability lists evidence, level
demonstrated, limitation, and what the next level would require. This does **not**
convert project evidence into inflated seniority claims — see
[engineering-evidence-ledger.md](../handoff/engineering-evidence-ledger.md) for
the full ledger.

Level scale: **Demonstrated** (proven in Atlas) · **Partial** (shown at synthetic
scale/one path) · **Not shown**.

## SQL & warehousing

Advanced SQL, grain, dedup, late data, incremental, partitioning, clustering,
dimensional modeling, cost control — **Demonstrated** (dbt models, `fct_events`
grain, incremental, partition pruning). *Limitation:* synthetic 50k rows.
*Next level:* production volume + slot/cost tuning under real load.

## dbt

Sources, staging, intermediate, facts, dimensions, marts, tests, contracts, docs,
incremental, schema evolution — **Demonstrated** (`dbt/atlas_dbt` + Sprint 7
schema checker). *Limitation:* single project. *Next level:* dbt mesh / multi-project.

## GCP

Cloud Storage, BigQuery, IAM, WIF, Composer, Logging, Monitoring, cost
stewardship — **Demonstrated** (Sprints 1–7 live evidence). *Limitation:* single
project, ephemeral Composer, one blocked IAM reduction. *Next level:* multi-env
promotion + live least-privilege proof.

## Pipeline engineering

Ingestion, idempotency, retries, backfills, orchestration, audit, failure
handling, recovery — **Demonstrated** (Sprints 1/3/6 + verified recovery).
*Limitation:* batch only. *Next level:* streaming/event-driven.

## Software engineering

Git, PRs, CI, lint, typing, tests, packaging, immutable releases, rollback —
**Demonstrated** (21-gate CI, 269-test unit+Airflow gate / 282 across all
suites, immutable bundles, rollback).
*Limitation:* single repo. *Next level:* multi-service release orchestration.

## Governance & security

Ownership, contracts, lineage, impact, schema compatibility, least privilege,
secrets, retention — **Demonstrated** (Sprint 7). *Limitation:* least privilege
not proven at permission level live (RISK-01/02, BLOCKED). *Next level:* execute
the IAM reduction + negative test.

## Operations

Alerts, runbooks, incidents, postmortems, recovery, verification, recurrence
prevention — **Demonstrated** (Sprints 5/6 drills + incident reports).
*Limitation:* representative live subset. *Next level:* sustained on-call at scale.

## Honest framing

Atlas is strong, reproducible **evidence of capability at a deliberately modest
synthetic scale**. It is not evidence of production-scale operation, enterprise
governance, or senior tenure. Blocked and unproven items are listed in
[unresolved-risks.md](unresolved-risks.md) and never counted as demonstrated.
