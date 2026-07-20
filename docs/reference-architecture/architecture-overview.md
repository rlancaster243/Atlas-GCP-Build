# Architecture Overview

**Status:** CURRENT · **Audience:** engineer, reviewer · **Source of truth:**
code + `docs/architecture-sprint{1..7}.md` + ADRs. Curated map; links to detail.

Atlas has four cooperating flows. Each is implemented and evidenced; none is
aspirational. Scale is synthetic — this is production-*oriented* evidence, not
proof of production traffic volume.

## 1. Data flow

```
event generation            src/atlas/generator (deterministic, seeded anomalies)
  → immutable raw artifact   JSONL, content-addressed per run
  → Cloud Storage            run-scoped, immutable landing paths
  → BigQuery raw             atlas_raw.events (partitioned by date, clustered)
  → dbt staging              stg_events (typed, normalized)
  → classification           int_event_classification (accept/reject + dup/replay)
  → accepted / rejected      int_accepted_events / int_rejected_events
  → fact + dimensions        fct_events (1 row/event_id), dim_users, dim_countries
  → marts                    mart_daily_event_metrics
  → operational evidence     atlas_ops.* (audit, quality, deployments, ...)
```

Invariants: raw is immutable and run-scoped; `fct_events` grain is one row per
`event_id`; accepted + rejected reconciles to raw under declared semantics;
quality failure blocks publication. Details:
[architecture-invariants.md](architecture-invariants.md), ADR-003/006.

## 2. Control flow (CI/CD)

```
pull request
  → credentialless CI        scripts/validate_ci.sh (21 gates, no GCP creds)
  → trusted integration      WIF-authenticated workflow (no service-account keys)
  → immutable release        build_deployment_bundle.sh (content-pinned bundle)
  → migration validation     apply_atlas_migrations.sh + checksums.lock
  → Composer deployment      deploy_atlas_release.sh (ephemeral environment)
  → smoke validation         validate_atlas_deployment.sh (gates success)
  → rollback OR success      rollback_atlas.sh (schema-compatibility checked)
```

Invariants: PR CI stays credentialless; releases are immutable; migrations run
before deployment validation; a failed deployment cannot publish success;
rollback checks schema compatibility. Details: ADR-008/009/010,
[ci-cd-runbook-sprint4.md](../ci-cd-runbook-sprint4.md).

## 3. Operational flow

```
pipeline telemetry           structured JSON logs w/ correlation ids
  → operational audit         atlas_ops.pipeline_runs / task_events / quality_results
  → Cloud Logging             atlas-events log + linked BigQuery dataset
  → metrics                   custom + log-based metrics (observability/metrics)
  → alerts                    Cloud Monitoring policies (observability/alerts)
  → investigation             runbook-driven diagnosis
  → recovery action           atlas_ops.recovery_actions (targeted repair)
  → verification              validate_warehouse; SUCCESS gated on VERIFIED
  → prevention evidence       incident reports + follow-ups
```

Invariants: operational history is durable; failures correlate by
`pipeline_run_id`/`batch_id`; recovery success requires verification; alerts map
to runbooks. Details: ADR-011/014, [observability-runbook-sprint5.md](../observability-runbook-sprint5.md),
[recovery-runbook-sprint6.md](../recovery-runbook-sprint6.md).

## 4. Governance flow

```
asset metadata               dbt meta.governance + governance/non_dbt_assets.yml
  → contract validation       gate_governance (owners, grain, classification, ...)
  → schema compatibility       atlas.governance.schema_check + baseline manifest
  → lineage impact             atlas.governance.lineage / impact
  → CI enforcement             5 offline gates in validate_ci.sh
  → controlled change          change record + consumer-impact evidence
```

Invariants: one source of truth for model governance; owners+grain required;
schema changes classified; breaking changes need migration + impact; permanent
evidence cannot receive transient retention; secrets never in evidence. Details:
ADR-016–020, [architecture-sprint7.md](../architecture-sprint7.md).

## What did NOT change across sprints

The Sprint 1 data plane shape (generate → GCS → raw → dbt → marts) is stable.
Later sprints added orchestration, delivery, observability, resilience, and
governance *around* it without redesigning it. The only data-plane semantics
change in Sprint 7 was duplicate/replay *classification* (ADR-006 amendment) —
the `fct_events` grain was preserved.
