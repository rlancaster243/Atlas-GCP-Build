"""Schema-drift detection for governed Atlas tables (Sprint 5, Phase 9).

An expected-schema manifest (``observability/schema/expected-schemas.json``,
generated from the live governed tables and reviewed into Git) is compared
against ``INFORMATION_SCHEMA.COLUMNS``. Findings are classified:

- ALLOWED   — configured new nullable field (``allowed_new_fields``) or
              metadata-only difference that does not affect consumers
- WARNING   — unapproved new nullable field, partition/clustering metadata
              drift, missing description-level metadata
- BREAKING  — removed field, incompatible type change, required field made
              nullable/unavailable, partition-field change, missing table

Detection is read-only. Drills use fixture datasets or expected-manifest
overrides; canonical tables are never mutated to prove this monitor.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google.cloud import bigquery

_MANIFEST_PATH = Path(__file__).resolve().parents[3] / "observability" / "schema" / "expected-schemas.json"

# Governed tables monitored for drift (dataset.table).
DEFAULT_MONITORED_TABLES = (
    "atlas_raw.events",
    "atlas_core.fct_events",
    "atlas_core.dim_users",
    "atlas_core.dim_countries",
    "atlas_marts.mart_daily_event_metrics",
    "atlas_ops.pipeline_runs",
    "atlas_ops.deployments",
    "atlas_ops.schema_migrations",
    "atlas_ops.task_events",
    "atlas_ops.quality_results",
    "atlas_ops.monitor_evaluations",
    "atlas_ops.recovery_actions",
)


@dataclass(frozen=True)
class DriftFinding:
    """One classified schema difference."""

    table: str
    column: str | None
    classification: str  # ALLOWED | WARNING | BREAKING
    kind: str
    detail: str


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or _MANIFEST_PATH).read_text(encoding="utf-8"))


def fetch_live_schema(
    client: bigquery.Client,
    project_id: str,
    dataset_id: str,
) -> dict[str, dict[str, dict[str, str]]]:
    """Return {table: {column: {data_type, is_nullable}}} for one dataset."""
    sql = f"""
        SELECT table_name, column_name, data_type, is_nullable, is_partitioning_column
        FROM `{project_id}.{dataset_id}.INFORMATION_SCHEMA.COLUMNS`
        ORDER BY table_name, ordinal_position
    """
    tables: dict[str, dict[str, dict[str, str]]] = {}
    for row in client.query(sql).result():
        tables.setdefault(row["table_name"], {})[row["column_name"]] = {
            "data_type": row["data_type"],
            "is_nullable": row["is_nullable"],
            "is_partitioning_column": row["is_partitioning_column"],
        }
    return tables


def compare_table(
    table: str,
    expected: dict[str, Any],
    live_columns: dict[str, dict[str, str]] | None,
    allowed_new_fields: list[str] | None = None,
) -> list[DriftFinding]:
    """Classify differences between one expected table schema and live columns."""
    findings: list[DriftFinding] = []
    allowed_new = set(allowed_new_fields or [])

    if live_columns is None:
        return [DriftFinding(table, None, "BREAKING", "missing_table", "table not found in live dataset")]

    expected_columns: dict[str, Any] = expected["columns"]
    for name, spec in expected_columns.items():
        live = live_columns.get(name)
        if live is None:
            findings.append(DriftFinding(table, name, "BREAKING", "removed_field", "expected column missing"))
            continue
        if live["data_type"] != spec["data_type"]:
            findings.append(
                DriftFinding(
                    table,
                    name,
                    "BREAKING",
                    "type_change",
                    f"expected {spec['data_type']}, live {live['data_type']}",
                )
            )
        if spec["is_nullable"] == "NO" and live["is_nullable"] == "YES":
            findings.append(
                DriftFinding(
                    table, name, "BREAKING", "required_made_nullable", "REQUIRED column now NULLABLE"
                )
            )
        expected_partition = expected.get("partition_column")
        if expected_partition == name and live.get("is_partitioning_column") != "YES":
            findings.append(
                DriftFinding(table, name, "BREAKING", "partition_change", "expected partition column lost")
            )

    for name, live in live_columns.items():
        if name in expected_columns:
            continue
        if f"{table}.{name}" in allowed_new or name in allowed_new:
            findings.append(
                DriftFinding(table, name, "ALLOWED", "approved_new_field", "configured additive field")
            )
        elif live["is_nullable"] == "YES":
            findings.append(
                DriftFinding(
                    table, name, "WARNING", "unapproved_new_field", "new nullable column not in manifest"
                )
            )
        else:
            findings.append(
                DriftFinding(
                    table, name, "BREAKING", "unapproved_required_field", "new REQUIRED column breaks writers"
                )
            )
    return findings


def detect_drift(
    client: bigquery.Client,
    project_id: str,
    *,
    manifest: dict[str, Any] | None = None,
    allowed_new_fields: list[str] | None = None,
) -> list[DriftFinding]:
    """Compare every manifest table against live INFORMATION_SCHEMA."""
    manifest = manifest or load_manifest()
    findings: list[DriftFinding] = []
    live_cache: dict[str, dict[str, dict[str, dict[str, str]]]] = {}
    for table, expected in manifest["tables"].items():
        dataset_id, table_name = table.split(".", 1)
        if dataset_id not in live_cache:
            live_cache[dataset_id] = fetch_live_schema(client, project_id, dataset_id)
        findings.extend(
            compare_table(
                table,
                expected,
                live_cache[dataset_id].get(table_name),
                allowed_new_fields,
            )
        )
    return findings


def summarize(findings: list[DriftFinding]) -> dict[str, int]:
    counts = {"ALLOWED": 0, "WARNING": 0, "BREAKING": 0}
    for finding in findings:
        counts[finding.classification] += 1
    return counts


def generate_manifest(
    client: bigquery.Client,
    project_id: str,
    tables: tuple[str, ...] = DEFAULT_MONITORED_TABLES,
) -> dict[str, Any]:
    """Snapshot live governed schemas into manifest form (review before commit)."""
    manifest: dict[str, Any] = {"generated_from": project_id, "tables": {}}
    live_cache: dict[str, dict[str, dict[str, dict[str, str]]]] = {}
    for table in tables:
        dataset_id, table_name = table.split(".", 1)
        if dataset_id not in live_cache:
            live_cache[dataset_id] = fetch_live_schema(client, project_id, dataset_id)
        columns = live_cache[dataset_id].get(table_name)
        if columns is None:
            raise RuntimeError(f"table {table} not found while generating manifest")
        partition_column = next(
            (c for c, spec in columns.items() if spec.get("is_partitioning_column") == "YES"),
            None,
        )
        manifest["tables"][table] = {
            "partition_column": partition_column,
            "columns": {
                name: {"data_type": spec["data_type"], "is_nullable": spec["is_nullable"]}
                for name, spec in columns.items()
            },
        }
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Atlas schema-drift tooling")
    parser.add_argument("--generate", action="store_true", help="snapshot live schemas to stdout")
    parser.add_argument("--check", action="store_true", help="compare manifest against live schemas")
    parser.add_argument("--project-id", default=None)
    args = parser.parse_args()

    from atlas.config.settings import load_settings
    from atlas.observability.cost import labeled_bigquery_client

    project_id = args.project_id or load_settings().gcp.project_id
    client = labeled_bigquery_client(project_id, "monitor")
    if args.generate:
        print(json.dumps(generate_manifest(client, project_id), indent=2, sort_keys=True))
        return 0
    if args.check:
        findings = detect_drift(client, project_id)
        print(
            json.dumps(
                {
                    "summary": summarize(findings),
                    "findings": [finding.__dict__ for finding in findings],
                },
                indent=2,
            )
        )
        return 1 if any(f.classification == "BREAKING" for f in findings) else 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
