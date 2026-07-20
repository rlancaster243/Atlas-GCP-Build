# Project Atlas Folder Structure

## Top level

| Path | Purpose |
| --- | --- |
| `config/` | Runtime YAML and seeded anomaly profile |
| `data/` | Generated JSONL artifacts |
| `docs/` | Architecture, setup, runbook, design review |
| `logs/` | Structured pipeline logs |
| `scripts/` | Cloud Shell CLI entry points |
| `sql/` | BigQuery DDL |
| `src/atlas/` | Python package |
| `tests/` | Automated tests |

## Python package

| Module | Responsibility |
| --- | --- |
| `config/settings.py` | Load settings and env overrides |
| `logging/structured.py` | JSON logging and step timing |
| `generator/events.py` | Synthetic event generation |
| `ingestion/upload.py` | Immutable GCS upload |
| `loader/bigquery.py` | Dataset/table creation and load |
| `validation/checks.py` | Quality checks and acceptance logic |
| `pipeline/orchestrator.py` | End-to-end sequencing |

## Scripts

| Script | Runs independently | Notes |
| --- | --- | --- |
| `generate_events.py` | Yes | Local only |
| `upload_events.py` | Yes | Requires GCP credentials |
| `load_events.py` | Yes | Requires GCS URI |
| `validate_events.py` | Yes | Requires loaded run |
| `run_pipeline.py` | Yes | Approval gated |
| `bootstrap_gcp.sh` | Yes | Approval gated |
| `verify_mcp_access.sh` | Yes | Desktop and cloud MCP checks |
| `simulate_failures.py` | Yes | Failure scenarios |

## Why this structure

The layout mirrors a small data platform team repo: config and docs at the top,
executable scripts for operators, importable Python modules for tests, and SQL kept
separate for future dbt reuse.

Common failure mode: opening `` as the Cursor workspace root will
not load repository-level MCP servers. Always open `de-project-1` at the root.
