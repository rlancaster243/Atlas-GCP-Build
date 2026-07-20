# Project Atlas Runbook

## Normal operation

```bash
cd Atlas-GCP-Build
export PYTHONPATH=src
export GCP_PROJECT_ID=example-gcp-project
python scripts/run_pipeline.py --approve-provision
```

Expected outcome:

- JSONL generated locally
- GCS object created under run-scoped prefix
- Rows loaded into `atlas_raw.events`
- Validation overall status: `FAIL` (seeded anomalies present)
- Acceptance anomaly detection checks: `PASS`

## Approval gate

Live GCP mutations require explicit approval:

```bash
export ATLAS_APPROVE_PROVISION=true
```

Without this variable:

- `bootstrap_gcp.sh` exits with code `2`
- `run_pipeline.py` exits with code `2`

## Recovery procedures

### Duplicate upload

Symptom: upload returns `already_exists=true`.

Action: inspect the existing object path in logs and either reuse the same
`pipeline_run_id` for downstream load or generate a new run id for a fresh object.

### Missing source file

Symptom: generator output path missing.

Action:

```bash
python scripts/generate_events.py
```

Re-run upload/load with the new local path.

### Bad schema load failure

Symptom: BigQuery load job fails.

Action:

1. Inspect load job error in Cloud Console or `bq ls -j --max_results=5`.
2. Fix JSONL schema locally.
3. Re-run with a new `pipeline_run_id`.

### Duplicate run load

Symptom: loader returns `already_loaded=true`.

Action: this is expected for idempotent replays. Validation can be re-run safely:

```bash
python scripts/validate_events.py --run-id <run-id> --event-date <YYYY-MM-DD>
```

### Null IDs and bad timestamps

Symptom: validation checks `null_user_ids`, `future_timestamps`, or
`late_arriving_events` report `FAIL`.

Action: for Sprint 1 this is expected. Confirm acceptance checks prove the seeded
counts were detected.

## Logs

Structured JSON logs are written to:

```text
logs/<pipeline_run_id>.jsonl
```

Each step records:

- timestamp
- duration
- status
- rows processed
- pipeline run id
- source file

## MCP troubleshooting

```bash
bash scripts/verify_mcp_access.sh
```

Common fixes:

- Restart Cursor after editing `.env`
- Run `gcloud auth application-default login` on desktop
- Ensure `ATLAS_GCP_SERVICE_ACCOUNT_KEY` is set for cloud agents
- Confirm workspace root is `de-project-1`, not `project-atlas`

## Manual verification queries

```bash
bq query --use_legacy_sql=false \
'SELECT COUNT(*) AS row_count FROM `example-gcp-project.atlas_raw.events` WHERE pipeline_run_id = "<run-id>"'
```

```bash
gsutil ls gs://atlas-raw-events-example-gcp-project/raw/**
```
