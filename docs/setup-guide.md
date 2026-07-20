# Project Atlas Setup Guide

## Prerequisites

- Google Cloud project: `example-gcp-project`
- Cloud Shell or local shell with Python 3.12
- Cursor workspace opened at repository root `de-project-1`
- Access to BigQuery and Cloud Storage in the sandbox project

## 1. Clone and enter Atlas

```bash
git clone https://github.com/YOUR_GITHUB_OWNER/de-project-1.git
cd de-project-1/project-atlas
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=src
```

## 2. Configure credentials

### Cursor Desktop

```bash
cp ../.env.example ../.env
gcloud auth application-default login
bash scripts/verify_mcp_access.sh
```

Restart Cursor and confirm **Settings → MCP** shows green for `bigquery` and `dbt`.

### Cursor Cloud Agents

1. Create a least-privilege service account in `example-gcp-project`.
2. Grant:
   - `roles/storage.objectAdmin` on the Atlas bucket
   - `roles/bigquery.dataEditor` on dataset `atlas_raw`
   - `roles/bigquery.jobUser` at project scope
3. Store base64-encoded JSON in Cursor secret `ATLAS_GCP_SERVICE_ACCOUNT_KEY`.
4. Re-run the cloud agent after secret injection.

## 3. Bootstrap GCP resources (approval gated)

```bash
export ATLAS_APPROVE_PROVISION=true
bash scripts/bootstrap_gcp.sh
```

This creates:

- Bucket `atlas-raw-events-example-gcp-project`
- Dataset `atlas_raw`
- Table `events` partitioned by `event_date`

## 4. Execute Sprint 1 locally

```bash
python scripts/generate_events.py
pytest
```

## 5. Execute Sprint 1 against GCP

```bash
python scripts/run_pipeline.py --approve-provision
python scripts/validate_events.py --run-id <run-id> --event-date <YYYY-MM-DD>
```

## Environment variables

| Variable | Purpose |
| --- | --- |
| `GCP_PROJECT_ID` | Sandbox project id |
| `ATLAS_GCP_PROJECT_ID` | Atlas override for project id |
| `ATLAS_GCS_BUCKET` | Physical bucket name |
| `ATLAS_APPROVE_PROVISION` | Required for bootstrap and live pipeline |
| `ATLAS_GCP_SERVICE_ACCOUNT_KEY` | Base64 SA JSON for cloud agents |
| `ATLAS_RANDOM_SEED` | Generator seed override |
| `ATLAS_EVENT_COUNT` | Generator count override |

## Verification checklist

- [ ] `pytest` passes locally
- [ ] `bash scripts/verify_mcp_access.sh` succeeds
- [ ] Cursor MCP servers are green
- [ ] Bootstrap completes with approval gate
- [ ] Pipeline generates logs under `logs/`
- [ ] Validation overall status is `FAIL`
- [ ] Acceptance anomaly detection checks are `PASS`
