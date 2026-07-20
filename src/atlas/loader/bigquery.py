"""BigQuery loader for Project Atlas Sprint 1.

Purpose:
    Create dataset/table if missing, load JSONL from GCS, append metadata, and
    preserve partition and cluster definitions.

Interactions:
    Reads GCS objects uploaded by ingestion and writes to ``atlas_raw.events``.
    Uses run-scoped staging tables to make replays idempotent.

Engineering principles:
    - Append-only raw layer compatible with future dbt staging models.
    - Explicit metadata columns for lineage and recovery.

Common failure modes:
    - Missing dataset or load job permissions.
    - Duplicate batch attempted twice (guarded by batch check).
    - Schema mismatch between JSONL and table definition.

Implementation choice:
    Load JSON to a run-scoped staging table, then INSERT into the partitioned
    target table. Alternatives considered: direct append load (weaker replay
    control) and external tables (less explicit metadata enrichment).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from atlas.config.settings import AtlasSettings, staging_table_id, table_fqn
from atlas.observability.cost import labeled_bigquery_client

RAW_SCHEMA = [
    bigquery.SchemaField("event_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("user_id", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("event_name", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("event_timestamp", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("event_date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("country_code", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("platform", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("app_version", "STRING", mode="NULLABLE"),
]

TARGET_SCHEMA = RAW_SCHEMA + [
    bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("source_file", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("pipeline_run_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("batch_id", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("processing_date", "DATE", mode="NULLABLE"),
]


@dataclass(frozen=True)
class BatchLoadState:
    """Existing raw rows for one stable batch identifier."""

    row_count: int
    ingestion_run_count: int


@dataclass(frozen=True)
class LoadResult:
    """Summary of a BigQuery load operation."""

    rows_loaded: int
    target_table: str
    staging_table: str
    already_loaded: bool
    source_file: str
    batch_id: str | None = None


def render_create_table_sql(settings: AtlasSettings) -> str:
    """Render the create-table SQL template."""
    template_path = Path(__file__).resolve().parents[3] / "sql" / "create_events_table.sql"
    template = template_path.read_text(encoding="utf-8")
    return template.format(
        project_id=settings.gcp.project_id,
        dataset_id=settings.gcp.dataset_id,
        table_id=settings.gcp.table_id,
    )


def ensure_dataset(client: bigquery.Client, settings: AtlasSettings) -> None:
    """Create the raw dataset if it does not exist."""
    dataset_ref = bigquery.Dataset(f"{settings.gcp.project_id}.{settings.gcp.dataset_id}")
    dataset_ref.location = settings.gcp.location
    try:
        client.get_dataset(dataset_ref.dataset_id)
    except NotFound:
        client.create_dataset(dataset_ref, exists_ok=True)


def ensure_events_table(client: bigquery.Client, settings: AtlasSettings) -> None:
    """Create the partitioned events table if it does not exist."""
    ensure_dataset(client, settings)
    table_id = table_fqn(settings)
    try:
        client.get_table(table_id)
    except NotFound:
        table = bigquery.Table(table_id, schema=TARGET_SCHEMA)
        table.time_partitioning = bigquery.TimePartitioning(field="event_date")
        table.clustering_fields = ["event_name", "country_code"]
        client.create_table(table)


def apply_sprint3_migration(client: bigquery.Client, settings: AtlasSettings) -> None:
    """Apply additive batch_id migration when needed."""
    migration_path = Path(__file__).resolve().parents[3] / "sql" / "migrate_sprint3.sql"
    rendered = migration_path.read_text(encoding="utf-8").format(
        project_id=settings.gcp.project_id,
        dataset_id=settings.gcp.dataset_id,
    )
    client.query(rendered).result()


def batch_load_state(
    client: bigquery.Client,
    settings: AtlasSettings,
    batch_id: str,
) -> BatchLoadState:
    """Return existing raw row counts for one batch identifier."""
    query = f"""
        SELECT
          COUNT(1) AS row_count,
          COUNT(DISTINCT pipeline_run_id) AS ingestion_run_count
        FROM `{table_fqn(settings)}`
        WHERE batch_id = @batch_id
    """
    rows = list(
        client.query(
            query,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter("batch_id", "STRING", batch_id)]
            ),
        ).result()
    )
    if not rows:
        return BatchLoadState(row_count=0, ingestion_run_count=0)
    return BatchLoadState(
        row_count=int(rows[0]["row_count"] or 0),
        ingestion_run_count=int(rows[0]["ingestion_run_count"] or 0),
    )


def run_already_loaded(client: bigquery.Client, settings: AtlasSettings, run_id: str) -> bool:
    """Return True when the target table already contains rows for a run."""
    query = f"""
        SELECT COUNT(1) AS row_count
        FROM `{table_fqn(settings)}`
        WHERE pipeline_run_id = @run_id
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("run_id", "STRING", run_id)]
    )
    rows = list(client.query(query, job_config=job_config).result())
    return bool(rows and rows[0]["row_count"] > 0)


def evaluate_batch_load(
    state: BatchLoadState,
    expected_row_count: int,
) -> str:
    """Return load action: load, skip, or fail."""
    if state.row_count == 0:
        return "load"
    if state.row_count == expected_row_count:
        return "skip"
    if 0 < state.row_count < expected_row_count:
        raise ValueError(f"Partial batch detected: expected {expected_row_count}, found {state.row_count}")
    raise ValueError(f"Conflicting batch detected: expected {expected_row_count}, found {state.row_count}")


def load_events_from_gcs(
    settings: AtlasSettings,
    gcs_uri: str,
    source_file: str,
    run_id: str,
    *,
    client: bigquery.Client | None = None,
    batch_id: str | None = None,
    processing_date: str | None = None,
    expected_row_count: int | None = None,
) -> LoadResult:
    """Load a GCS JSONL file into the partitioned events table."""
    bq_client = client or labeled_bigquery_client(settings.gcp.project_id, "ingestion")
    ensure_events_table(bq_client, settings)
    apply_sprint3_migration(bq_client, settings)

    expected_rows = expected_row_count or settings.validation.expected_event_count

    if batch_id is not None:
        state = batch_load_state(bq_client, settings, batch_id)
        action = evaluate_batch_load(state, expected_rows)
        if action == "skip":
            return LoadResult(
                rows_loaded=0,
                target_table=table_fqn(settings),
                staging_table="",
                already_loaded=True,
                source_file=source_file,
                batch_id=batch_id,
            )
    elif run_already_loaded(bq_client, settings, run_id):
        return LoadResult(
            rows_loaded=0,
            target_table=table_fqn(settings),
            staging_table="",
            already_loaded=True,
            source_file=source_file,
            batch_id=batch_id,
        )

    staging_id = staging_table_id(settings, run_id)
    staging_fqn = f"{settings.gcp.project_id}.{settings.gcp.dataset_id}.{staging_id}"
    staging_table = bigquery.Table(staging_fqn, schema=RAW_SCHEMA)
    bq_client.delete_table(staging_table, not_found_ok=True)
    bq_client.create_table(staging_table)

    load_job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        schema=RAW_SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        ignore_unknown_values=True,
    )
    load_job = bq_client.load_table_from_uri(gcs_uri, staging_fqn, job_config=load_job_config)
    load_job.result()

    ingested_at = datetime.now(tz=UTC).isoformat()
    insert_sql = f"""
        INSERT INTO `{table_fqn(settings)}` (
          event_id,
          user_id,
          event_name,
          event_timestamp,
          event_date,
          country_code,
          platform,
          app_version,
          ingested_at,
          source_file,
          pipeline_run_id,
          batch_id,
          processing_date
        )
        SELECT
          event_id,
          user_id,
          event_name,
          event_timestamp,
          event_date,
          country_code,
          platform,
          app_version,
          TIMESTAMP(@ingested_at) AS ingested_at,
          @source_file AS source_file,
          @run_id AS pipeline_run_id,
          @batch_id AS batch_id,
          DATE(@processing_date) AS processing_date
        FROM `{staging_fqn}`
    """
    query_job = bq_client.query(
        insert_sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("ingested_at", "STRING", ingested_at),
                bigquery.ScalarQueryParameter("source_file", "STRING", source_file),
                bigquery.ScalarQueryParameter("run_id", "STRING", run_id),
                bigquery.ScalarQueryParameter("batch_id", "STRING", batch_id),
                bigquery.ScalarQueryParameter("processing_date", "STRING", processing_date),
            ]
        ),
    )
    query_job.result()
    inserted_rows = query_job.num_dml_affected_rows or 0
    bq_client.delete_table(staging_table, not_found_ok=True)

    return LoadResult(
        rows_loaded=inserted_rows,
        target_table=table_fqn(settings),
        staging_table=staging_fqn,
        already_loaded=False,
        source_file=source_file,
        batch_id=batch_id,
    )
