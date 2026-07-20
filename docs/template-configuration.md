# Template Configuration

## Required runtime parameters

| Parameter | Purpose |
| --- | --- |
| `ATLAS_GCP_PROJECT_ID` | Target GCP project |
| `ATLAS_GCP_PROJECT_NUMBER` | Numeric project identifier for WIF/IAM |
| `ATLAS_GCP_LOCATION` | BigQuery multi-region or region |
| `ATLAS_GCP_REGION` | Regional services such as Composer |
| `ATLAS_GCS_BUCKET` | Immutable raw-ingestion bucket |
| `ATLAS_RELEASE_BUCKET` | Immutable release-bundle bucket |
| `ATLAS_DATASET_PREFIX` | Prefix for BigQuery datasets |
| `ATLAS_SERVICE_ACCOUNT_PREFIX` | Prefix for provisioned identities |
| `ATLAS_DAG_ID` | Airflow DAG identifier |
| `ATLAS_SCHEDULE` | Airflow schedule |
| `ATLAS_NOTIFICATION_EMAIL` | Operator notification destination |
| `ATLAS_COST_CEILING_BYTES` | Pre-execution query guard |

## GitHub repository variables

Trusted workflows require:

- `ATLAS_WIF_PROVIDER`
- `ATLAS_INTEGRATION_SERVICE_ACCOUNT`
- `ATLAS_DEPLOYER_SERVICE_ACCOUNT`

Pull-request CI must remain credentialless. Do not add cloud credentials to PR
workflows merely because authentication is annoying. Authentication is supposed
to be annoying when the alternative is accidental infrastructure mutation.

## Adoption gate

Before calling an adoption complete, prove:

1. clean clone and static CI
2. isolated GCP deployment
3. successful batch and warehouse reconciliation
4. deliberate failure and targeted recovery
5. alerts and runbook routing
6. schema compatibility behavior
7. IAM and secret review
8. cost ceiling and cleanup
9. operator handoff
