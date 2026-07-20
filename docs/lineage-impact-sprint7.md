# Atlas Lineage & Consumer Impact (Sprint 7)

Lineage and consumer-impact analysis derived entirely from **repository
artifacts** — no graph database, metadata service, or web UI (out of scope).

## Sources of truth

- dbt model SQL `ref()` / `source()` calls (the model DAG).
- `governance/consumers.yml` (internal downstream consumers).
- `governance/generated/catalog.json` (owners, contracts, runbooks).

## Lineage

```bash
python -m atlas.governance.lineage --output governance/generated/lineage.json
```

Produces a machine-readable graph (`nodes` with `upstream`/`downstream`,
`edge_count`). Current graph: 26 nodes / 29 edges, covering
`atlas_raw.events → stg_events → int_event_classification →
int_accepted_events → fct_events → {dim_users, mart_daily_event_metrics} →
consumers`. `gate_lineage_impact` fails on drift or if the source→mart chain
breaks.

## Consumer impact

```bash
python -m atlas.governance.impact --asset fct_events \
    --change governance/changes/CHG-....yml --output-dir /tmp/impact
```

Emits `impact.json` + `impact.md` with:

1. source-to-mart position (upstream + downstream),
2. direct downstream assets,
3. transitive downstream assets,
4. affected tests / property files,
5. affected contracts (asset → contract_version),
6. affected consumers and owners to notify,
7. runbooks involved,
8. (with `--change`) the change's compatibility class + whether approval is
   present.

### Example (fct_events)

- Direct downstream: `mart_daily_event_metrics`, `warehouse_reconciliation`,
  `atlas_observability_monitor`.
- Transitive: adds `analytics_mart_readers`.
- Owners to notify: `atlas-data-eng`, `atlas-analytics`.
- Affected contracts: `fct_events 1.0`, `mart_daily_event_metrics 1.0`.

## How it plugs into change management

A BREAKING/CONDITIONALLY_COMPATIBLE change record (ADR-017) must reference the
impact report so reviewers see exactly which consumers require migration before
approval. This is the "consumer-impact analysis" that PROHIBITED changes bypass.

## Honest limitations

- Consumers are limited to what `consumers.yml` declares — external or
  undeclared consumers are not discovered.
- Lineage covers known Atlas assets (dbt DAG + registered non-dbt assets); it is
  not full warehouse-wide lineage.
