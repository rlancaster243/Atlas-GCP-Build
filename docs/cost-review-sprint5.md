# Atlas Sprint 5 Cost and Retention Review

Measurements below were taken live on 2026-07-19 during the Sprint 5
acceptance window in project `example-gcp-project`. Currency figures use
public list prices for `us-central1` at the time of writing and are estimates,
not billing-export truth.

## Composer (dominant cost, ephemeral)

| Item | Value |
| --- | --- |
| Environment | `atlas-dev`, `composer-3-airflow-3.1.7-build.13`, ENVIRONMENT_SIZE_SMALL |
| Created | 2026-07-19T03:44:08Z |
| Deleted | end of acceptance window (teardown gated on `ATLAS_APPROVE_TEARDOWN`) — recorded in the validation report |
| Estimated rate | ≈ $0.60–0.90/hour for a small Composer 3 environment (compute + storage + fees) |
| Acceptance window | single-digit hours ⇒ single-digit dollars |

Composer is deliberately not left running: per the owner's standing decision,
environments exist only for evidence capture. The observability design
tolerates that (`monitoring_enabled` + NO_DATA states distinguish "paused by
design" from "stale").

## Cloud Logging

| Item | Measured |
| --- | --- |
| Project log ingestion, trailing 24 h of acceptance | 57.2 MB (`logging.googleapis.com/billing/bytes_ingested`) |
| Largest sources | BigQuery data-access audit logs (~21 MB/6 h); Atlas structured events are a small fraction |
| `atlas-observability` bucket retention | 30 days, analytics enabled |
| `_Default` bucket retention | 30 days (unchanged) |
| Free tier | first 50 GiB/project/month ingestion free; current run-rate ≈ 1.7 GB/month ⇒ $0 marginal |

The Atlas sink is additive (no exclusions), so entries are counted once for
ingestion; duplicate routing to the dedicated bucket does not double the
ingestion bill (storage beyond retention defaults would, but 30 days is the
default free retention).

Justification for 30-day retention: Sprint drills and incident
reconstruction need at most a few weeks of history; durable operational truth
lives in BigQuery audit tables (`pipeline_runs`, `task_events`,
`quality_results`, `monitor_evaluations`, `deployments`), which are tiny (see
below). Longer log retention would add cost without a consumer.

## Cloud Monitoring

| Item | Measured |
| --- | --- |
| Custom metric descriptors | 15 (`custom.googleapis.com/atlas/...`) |
| Active `check_status` series | 22 = 11 checks × 2 modes (normal, drill) — within the documented cardinality budget (≤ 3 bounded labels per metric, no run/batch ids) |
| Other atlas metrics | 2–6 series each (mode × small label sets) |
| Ingested samples | one point per metric per monitor run (30-min cadence) ⇒ ~1.5 K samples/day total — far inside the 150 MB/month free allotment |
| Alert policies | 10 (no per-policy charge) |
| Notification channel | 1 email channel ($0) |
| Dashboard | 1 ("Atlas Operations", 31 tiles; $0) |

## BigQuery

| Item | Measured |
| --- | --- |
| `atlas_ops` dataset size | 0.09 MB across 6 tables |
| Monitor query cost | every check uses bounded time windows (30-day max) over KB-scale audit tables; the cost check reads `region-us.INFORMATION_SCHEMA.JOBS` bounded to its baseline window |
| Linked dataset (`atlas_logs`) | read-only view over the log bucket; queries bill as BigQuery scans of scanned log volume — trailing-hour drill queries scanned < 100 MB total |
| Job labeling | `application=atlas` labels + dbt `query-comment` enable attribution via `observability/queries/bigquery_cost.sql` |

## What was deleted vs retained after the acceptance window

Deleted (ephemeral):
- Composer environment `atlas-dev` (and alert policies expecting it are
  disabled first — see runbook teardown procedure).
- Drill-mode metric series stop receiving points (auto-age-out); a PASS
  recovery point was published to every drill series
  (`manage_atlas_alerts.sh delete-test-resources`).

Retained (permanent, near-zero cost):
- `atlas_ops` BigQuery tables (< 1 MB), `atlas_raw`/`atlas_core`/`atlas_marts`
  datasets (synthetic data, MB scale).
- Log bucket + sink + view + linked dataset (storage-bounded by 30-day
  retention).
- Metric descriptors, alert policies (disabled where their source
  intentionally disappears with Composer), dashboard, notification channel.
- Deployment bundles in GCS (immutable releases, MB scale each).

## Monthly projection (steady state, environment torn down)

| Component | Projection |
| --- | --- |
| Composer | $0 (no environment) |
| Logging | $0 (under free tier; 30-day retention) |
| Monitoring | $0–low single dollars (custom-metric samples under free tier) |
| BigQuery storage | ≈ $0.02 |
| BigQuery queries | $0 while the monitor DAG is not running (no environment); during acceptance windows, bounded queries on KB–MB tables |
| Total | effectively the cost of the acceptance windows themselves (Composer hours) |

## Guardrails verified

- No DEBUG logging enabled anywhere; Airflow logging level INFO.
- No unbounded monitor queries (every check has an explicit window).
- No batch/run ids or error strings as metric labels (CI-enforced cardinality
  gate + `validate_point` runtime contract).
- No raw event payloads logged; details are truncated at 4 KB.
- Single additive log sink; no duplicate sinks; `_Default` untouched.
- Dashboard is updated in place by display name, never re-created.
- The cost-anomaly drill used a synthetic drill-mode metric point, not real
  BigQuery spend.
