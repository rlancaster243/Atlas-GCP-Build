# Project Atlas Sprint 2 Runbook

## Prerequisites

- Sprint 1 raw table populated: `example-gcp-project.atlas_raw.events`
- GCP auth via `gcloud auth application-default login` or external service account key
- Cloud Shell or approved agent environment with `gcloud`, `bq`, and Python 3

## One-time setup

Run from `~/Atlas-GCP-Build/project-atlas` on branch `cursor/atlas-sprint-2-dbt-warehouse-3660`:

```bash
cd ~/Atlas-GCP-Build
git fetch origin cursor/atlas-sprint-2-dbt-warehouse-3660
git checkout cursor/atlas-sprint-2-dbt-warehouse-3660
cd Atlas-GCP-Build
export ATLAS_GCP_PROJECT_ID=example-gcp-project
export ATLAS_DBT_DATASET=atlas
bash scripts/setup_dbt.sh
```

The setup script creates `.venv-dbt`, installs pinned dbt packages, writes `~/.dbt/profiles.yml`
without printing credentials, and runs `dbt debug`.

## Full warehouse build

```bash
source .venv-dbt/bin/activate
bash scripts/run_dbt_sprint2.sh
```

Options:

- `--full-refresh` — rebuild incremental models from scratch
- `--skip-docs` — skip `dbt docs generate`

## Validation and evidence

```bash
bash scripts/validate_dbt_sprint2.sh
```

Writes `logs/validation-sprint2-<timestamp>.json` with counts, anomaly totals, and gate status.

## Incremental rerun (unchanged source)

After a successful full build against the validated run:

```bash
source .venv-dbt/bin/activate
dbt build --project-dir dbt/atlas_dbt --profiles-dir ~/.dbt --target dev
dbt test --project-dir dbt/atlas_dbt --profiles-dir ~/.dbt --target dev
```

Expect no new rows when the raw source is unchanged.

## Bounded backfill example

```bash
dbt run --select fct_events \
  --project-dir dbt/atlas_dbt \
  --profiles-dir ~/.dbt \
  --target dev \
  --vars '{"start_date": "2026-07-01", "end_date": "2026-07-14"}'
```

## Troubleshooting

| Symptom | Action |
| --- | --- |
| `dbt debug` auth failure | Re-run ADC login or set `GOOGLE_APPLICATION_CREDENTIALS` |
| Freshness warning/error | Expected if raw data is stale; investigate ingestion schedule |
| Singular anomaly test failure | Compare counts in `int_event_classification` against validated run scope |
| Contract enforcement failure | Inspect schema drift in staging/core YAML contracts |

## Security

- Never commit `profiles.yml`, service account JSON, or `.env`
- Scripts redact credentials from stdout
- Live profile generation requires explicit environment variables only
