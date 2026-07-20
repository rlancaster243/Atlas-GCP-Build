# Atlas Local Airflow (Sprint 3)

Local Airflow **3.1.7** with Composer-parity provider pins for DAG development and
acceptance testing before Composer deployment.

## Quick start

```bash
cd Atlas-GCP-Build
source airflow/airflow.env.example   # or copy to .env
bash scripts/setup_airflow.sh
bash scripts/start_airflow_local.sh
bash scripts/test_airflow_sprint3.sh
```

## Version pins

See [requirements-airflow.txt](requirements-airflow.txt) and [ADR-005](../docs/adr/ADR-005-airflow-composer-parity.md).

Target Composer image: `composer-3-airflow-3.1.7-build.12`.

## Layout

| Path | Purpose |
|------|---------|
| `../dags/` | DAG definitions and parse-time helpers |
| `../.airflow/` | Local metadata DB (gitignored) |
| `../.venv-airflow/` | Pinned virtualenv (gitignored) |
| `../logs/airflow/` | Run summaries and task evidence |

## Composer mapping

Deploy DAGs to `/home/airflow/gcs/dags/project_atlas/` and runtime assets to
`/home/airflow/gcs/data/` with `ATLAS_ROOT` pointing at the data path.
