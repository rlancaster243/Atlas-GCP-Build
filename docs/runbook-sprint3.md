# Atlas Sprint 3 Runbook

## Local setup

```bash
cd ~/Atlas-GCP-Build/project-atlas
git checkout cursor/atlas-sprint-3-airflow-orchestration-3660
export ATLAS_GCP_PROJECT_ID=example-gcp-project
source airflow/airflow.env.example
bash scripts/setup_airflow.sh
bash scripts/test_airflow_sprint3.sh
bash scripts/start_airflow_local.sh
# Cloud Shell: wait ~30s, then check DAG registration
tail -f .airflow/standalone.log
```

Cloud Shell has no tmux; `start_airflow_local.sh` falls back to `nohup` and writes
`.airflow/standalone.log`. Ensure `PYTHONPATH` includes `src/` and `dags/` (set in
`airflow.env.example`).

## Trigger a run

Start Airflow before triggering. `run_airflow_sprint3.sh` waits for the DAG to register.

```bash
bash scripts/run_airflow_sprint3.sh \
  --processing-date 2026-07-15 \
  --batch-id atlas-20260715 \
  --conf '{"upload_once": true}'
```

## Recovery

| Scenario | Action |
|----------|--------|
| Transient upload failure | Allow retry; verify audit row transitions to SUCCESS |
| dbt test failure | Clear failed task after fixing; rerun with new pipeline_run_id |
| Partial batch in raw | Investigate loader logs; do not clear without ops review |
| Audit table missing | Re-run `ensure_audit_resources` via DAG or CLI |

## Composer notes

- Deploy DAGs separately from data/scripts.
- Use environment service account with BigQuery + GCS permissions.
- SQLite limitations apply locally only; Composer uses Cloud SQL metadata.
