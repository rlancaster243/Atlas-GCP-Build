# Atlas Alert Catalog (Sprint 5)

All policies are repo-managed in `observability/alerts/*.json`, applied
idempotently by `scripts/manage_atlas_alerts.sh`, and routed to the verified
Cloud Monitoring email channel
`projects/example-gcp-project/notificationChannels/6567861337166986657`
("Atlas Primary Operator (email)"; the address is deliberately not committed).
Owner for every policy: the primary operator (primary operator).

All `check_status`-based policies share the same mechanics: the monitor DAG
publishes `custom.googleapis.com/atlas/monitor/check_status` (0 PASS / 1 WARN
/ 2 FAIL / −1 NO_DATA / −2 DISABLED) every 30 minutes per `check_name`; the
condition fires when max-aligned value > 1.5 (10-minute alignment, retest on
each new point); incidents auto-close 30 minutes after cessation. Test method:
`manage_atlas_alerts.sh test <check_name>` publishes a synthetic FAIL on the
`mode=drill` series (drill series never pollute normal history but evaluate
against the same policy, which is exactly what a drill needs).

| Policy (display name) | Signal (`check_name` unless noted) | Severity | Incident key | Runbook anchor | Main false-positive risk |
|---|---|---|---|---|---|
| Atlas: pipeline failed | `latest_run_state` | critical | `atlas-latest_run_state` | `#alert-atlas-pipeline-failed` | none known |
| Atlas: data stale | `freshness` (fail ≥ 50 h) | critical | `atlas-freshness` | `#alert-atlas-data-stale` | environment paused without disabling monitoring |
| Atlas: reconciliation failed | `reconciliation` | critical | `atlas-reconciliation` | `#alert-atlas-reconciliation-failed` | none known |
| Atlas: critical volume deviation | `volume_deviation` (fail ≥ 80 %) | critical | `atlas-volume_deviation` | `#alert-atlas-volume-deviation` | intentional batch-size change |
| Atlas: breaking schema drift | `schema_drift` | critical | `atlas-schema_drift` | `#alert-atlas-schema-drift` | manifest not regenerated after approved migration |
| Atlas: deployment failed | `deployment_failure` | critical | `atlas-deployment_failure` | `#alert-atlas-deployment-failed` | none known |
| Atlas: rollback failed | `rollback_failure` | critical | `atlas-rollback_failure` | `#alert-atlas-rollback-failed` | none known |
| Atlas: Composer environment unhealthy | native `composer.googleapis.com/environment/healthy` < 0.5 for 15 min | critical | `atlas-composer-unhealthy` | `#alert-atlas-composer-unhealthy` | creation/deletion transitions |
| Atlas: BigQuery cost anomaly | `cost_anomaly` (≥ 10× baseline and > 1 GiB) | warning | `atlas-cost_anomaly` | `#alert-atlas-cost-anomaly` | legitimate backfill bursts |
| Atlas: telemetry incomplete | `telemetry_completeness` | warning | `atlas-telemetry_completeness` | `#alert-atlas-telemetry-incomplete` | runs predating Sprint 5 telemetry |

Design rules in force:

- One policy per root cause; WARN states are dashboard-visible but only FAIL
  (value 2) pages, separating warning from critical.
- Metric absence is used nowhere as a fail signal: the freshness check makes
  staleness an explicit value, and the Composer policy conditions on an
  unhealthy value, so intentional teardown (metric absence) cannot fire it.
  Teardown checklist additionally disables `atlas-composer-unhealthy` and
  sets `monitoring_enabled: false` (all checks then publish DISABLED = −2).
- No stale-data alerting while `monitoring_enabled: false`.
- The cost drill uses a synthetic drill-series point, never real spend.
- Policy descriptions contain runbook paths and no secrets or addresses.
- `manage_atlas_alerts.sh apply` is idempotent (update-by-display-name);
  before editing a firing policy, capture the open incident evidence first.
