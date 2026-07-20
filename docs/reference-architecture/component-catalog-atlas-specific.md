# Component Catalog — Atlas-Specific

**Status:** CURRENT · **Audience:** engineer, reviewer, template author. These
components encode Atlas's synthetic domain or environment. A new project built
from the template would **replace** them. For each: why it is specific, what a
new project replaces it with, the interface that must stay stable, and which
reusable component depends on it.

Fields: why specific · new-project replacement · stable interface · reusable
dependency.

- **AC-01 synthetic event schema** (`src/atlas/generator`, `config/atlas.yaml`).
  Why: models a fictional user-action stream. Replace: real source schema.
  Stable interface: the raw-table column contract consumed by dbt sources.
  Depends: RC-09 logging, RC-16 governance (contract).
- **AC-02 anomaly injection profile** (`config/anomaly_profile.yaml`). Why: seeded
  test anomalies (50 within-batch duplicates, etc.). Replace: real data-quality
  expectations. Interface: `assert_source_anomaly_profile` inputs. Depends: RC-11.
- **AC-03 event identity rules** (event_id derivation). Why: synthetic id scheme.
  Replace: source primary key. Interface: INV-D2/D5. Depends: RC-17 schema check.
- **AC-04 acceptance/rejection semantics** (`int_event_classification`). Why:
  Atlas-defined validity rules. Replace: domain validity rules. Interface: INV-D6
  reconciliation. Depends: RC-16.
- **AC-05 `fct_events` grain** (one row/event_id). Why: Atlas fact definition.
  Replace: new fact grain. Interface: INV-D5. Depends: RC-17, RC-18.
- **AC-06 specific dimensions & marts** (`dim_users`, `dim_countries`,
  `mart_daily_event_metrics`). Why: Atlas domain model. Replace: new dims/marts.
  Interface: dbt contracts. Depends: RC-18 lineage.
- **AC-07 Atlas dataset names** (`atlas_raw`, `atlas_core`, `atlas_ops`, marts).
  Why: naming. Replace: `dataset_prefix` parameter. Interface: everywhere.
  Depends: RC-05/06/10/16.
- **AC-08 Atlas service-account names** (`atlas-github-integration`,
  deployer/runtime SAs). Why: identity naming. Replace: `service_account_prefix`.
  Interface: WIF bindings. Depends: RC-03.
- **AC-09 Atlas alert thresholds** (`observability/alerts/*.json`,
  `config/observability.yaml`). Why: tuned to 50k synthetic scale. Replace:
  real SLOs. Interface: RC-12 alert→runbook. Depends: RC-11/12.
- **AC-10 GCP project reference** (`example-gcp-project`). Why: this project.
  Replace: `gcp_project_id`. Interface: all cloud calls. Depends: RC-02/03.
- **AC-11 sample processing dates** (`2026-07-15`, `atlas-20260717`, ...). Why:
  demo batches. Replace: real schedule dates. Interface: DAG params. Depends: RC-11.
- **AC-12 Atlas dashboard content** (`observability/dashboards/`). Why: Atlas
  metrics layout. Replace: project dashboard. Depends: RC-11.
- **AC-13 Atlas-specific failure scenarios** (`config/failure_scenarios.yaml`).
  Why: tuned to Atlas pipeline. Replace: project scenarios. Depends: RC-14.

## Boundary rule

No component may be reclassified as reusable merely because it is written in
Python or YAML. If replacing the synthetic domain would require rewriting the
component's *logic* (not just its configuration), it belongs here. The
naming into parameters and keeps AC-01..AC-06 as project-supplied contracts.
