# Atlas GCP Production Data Platform Template

Atlas is a reusable, production-oriented batch data platform foundation for Google
Cloud. It combines Python ingestion, Cloud Storage, BigQuery, dbt, Airflow,
credentialless CI, controlled deployment, observability, recovery, governance,
and cost controls in one repository.

This is not a claim that cloning a repository magically makes a system production
ready. It provides enforced engineering defaults and operating artifacts that a
team must configure, validate, deploy, and own.

## Architecture

```text
Source / synthetic events
        ↓
Python ingestion → immutable Cloud Storage objects
        ↓
BigQuery raw tables
        ↓
dbt staging → classification/quarantine → facts/dimensions/marts
        ↓
Airflow orchestration, audit, retries, backfills, and recovery
        ↓
Logging, metrics, alerts, governance, lineage, cost guards, runbooks
```

## Included capabilities

- Deterministic sample event generation and idempotent batch ingestion
- Partitioned and clustered BigQuery storage
- Governed dbt layers, tests, contracts, and incremental processing
- Airflow DAGs with stable batch identity, retries, auditing, and backfills
- Credentialless pull-request CI
- Optional keyless GitHub-to-GCP delivery through Workload Identity Federation
- Immutable release bundles, migrations, smoke validation, and rollback
- Structured telemetry, metrics, alerts, dashboards, and runbooks
- Failure injection, recovery auditing, schema compatibility, and cost guards
- Ownership, lineage, consumer-impact, retention, security, and evidence controls

## Start here

1. Read [`START_HERE.md`](START_HERE.md).
2. Copy `.env.example` to `.env` and replace every example value.
3. Create a Python virtual environment and install dependencies.
4. Run credentialless static validation.
5. Run the local sample pipeline.
6. Configure an isolated GCP project before any approved cloud mutation.

```bash
git checkout main
git pull --ff-only origin main
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-ci.txt
export PYTHONPATH=src
bash scripts/validate_ci.sh --mode static
python scripts/generate_events.py
pytest
```

## Configuration

The template keeps the `atlas` reference namespace in code and sample assets,
while cloud identities and runtime resources are configured through environment
variables. See [`docs/template-configuration.md`](docs/template-configuration.md).

Never deploy the example values. Configure project IDs, buckets, datasets,
service accounts, notification channels, cost ceilings, retention, and schedules
for the adopting environment.

## CI and delivery

Pull requests run credentialless validation. Trusted integration and deployment
workflows are manual and require repository variables for Workload Identity
Federation:

- `ATLAS_WIF_PROVIDER`
- `ATLAS_INTEGRATION_SERVICE_ACCOUNT`
- `ATLAS_DEPLOYER_SERVICE_ACCOUNT`

The bootstrap scripts are plan-first and mutation-gated. Review IAM, cost, and
cleanup behavior before applying anything.

## Evidence and limitations

The original Atlas reference implementation was tested with synthetic workloads,
clean-clone validation, CI, controlled cloud deployments, failure drills, and
operator handoff. Those historical reports remain in `docs/` as engineering
evidence. They do not prove that a new adoption has passed the same gates.

The reference release lineage includes `atlas-sprint-3-complete` for the orchestrated platform milestone and later Sprint 8 handoff evidence.

A new deployment is complete only after its own CI, isolated cloud validation,
incident drill, recovery exercise, security review, cost review, and handoff.

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
