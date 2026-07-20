"""Idempotent creation of operational BigQuery resources."""

from __future__ import annotations

from pathlib import Path

from google.cloud import bigquery

from atlas.config.settings import AtlasSettings, load_settings
from atlas.observability.cost import labeled_bigquery_client


def _sql_path(name: str) -> Path:
    return Path(__file__).resolve().parents[3] / "sql" / name


def ensure_audit_resources(
    settings: AtlasSettings | None = None,
    *,
    client: bigquery.Client | None = None,
) -> None:
    """Create atlas_ops dataset and pipeline_runs table when missing."""
    settings = settings or load_settings()
    bq_client = client or labeled_bigquery_client(settings.gcp.project_id, "audit")
    schema_sql = (_sql_path("create_ops_schema.sql")).read_text(encoding="utf-8")
    table_sql = (_sql_path("create_pipeline_runs_table.sql")).read_text(encoding="utf-8")
    for template in (schema_sql, table_sql):
        rendered = template.format(
            project_id=settings.gcp.project_id,
            location=settings.gcp.location,
        )
        bq_client.query(rendered).result()

    # Verify the table exists after DDL.
    table_id = f"{settings.gcp.project_id}.atlas_ops.pipeline_runs"
    bq_client.get_table(table_id)
