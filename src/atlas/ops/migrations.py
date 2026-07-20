"""Ledger-driven additive schema migrations for Project Atlas.

Migrations are declared in ``sql/migrations/manifest.txt`` and applied in
manifest order. Every applied migration is recorded in
``atlas_ops.schema_migrations`` with the SHA-256 checksum of its source file:

- re-applying a recorded, unchanged migration is an idempotent no-op;
- a recorded migration whose file content changed fails hard;
- a failed migration is recorded as FAILED and blocks promotion.

Destructive changes are never reversed automatically (ADR-010).
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from google.cloud import bigquery

from atlas.config.settings import AtlasSettings, load_settings
from atlas.observability.cost import labeled_bigquery_client
from atlas.ops.audit import sanitize_error_message

SQL_ROOT = Path(__file__).resolve().parents[3] / "sql"
MANIFEST_PATH = SQL_ROOT / "migrations" / "manifest.txt"

_LEDGER_DDL = """
CREATE SCHEMA IF NOT EXISTS `{project_id}.atlas_ops` OPTIONS (location = '{location}');
CREATE TABLE IF NOT EXISTS `{project_id}.atlas_ops.schema_migrations` (
  migration_id STRING NOT NULL,
  migration_checksum STRING NOT NULL,
  git_sha STRING,
  applied_at TIMESTAMP NOT NULL,
  workflow_run_id STRING,
  applied_by STRING,
  status STRING NOT NULL,
  error_summary STRING
)
CLUSTER BY migration_id;
"""


@dataclass(frozen=True)
class Migration:
    """One manifest entry."""

    migration_id: str
    sql_path: Path
    checksum: str
    # Sprint 6 (ADR-015): a breaking migration makes releases built before it
    # ineligible as rollback targets — old runtimes cannot run against the
    # post-migration schema and a forward fix is required instead.
    breaking: bool = False


@dataclass(frozen=True)
class MigrationPlanEntry:
    """Planned action for one migration."""

    migration_id: str
    checksum: str
    state: str  # PENDING | APPLIED | CHECKSUM_MISMATCH | FAILED_PREVIOUSLY


def load_manifest(manifest_path: Path | None = None) -> list[Migration]:
    """Parse the migration manifest into ordered migrations."""
    path = manifest_path or MANIFEST_PATH
    migrations: list[Migration] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 2 or not parts[0] or not parts[1]:
            raise ValueError(f"Malformed manifest line: {line!r}")
        migration_id, rel_path = parts[0], parts[1]
        flags = set(parts[2:])
        if flags - {"breaking"}:
            raise ValueError(f"Unknown manifest flags {sorted(flags - {'breaking'})} on line: {line!r}")
        if migration_id in seen:
            raise ValueError(f"Duplicate migration id: {migration_id}")
        seen.add(migration_id)
        sql_path = (path.parent / rel_path).resolve()
        if not sql_path.is_file():
            raise FileNotFoundError(f"Migration {migration_id} references missing file {sql_path}")
        checksum = hashlib.sha256(sql_path.read_bytes()).hexdigest()
        migrations.append(
            Migration(
                migration_id=migration_id,
                sql_path=sql_path,
                checksum=checksum,
                breaking="breaking" in flags,
            )
        )
    return migrations


def render_migration_sql(migration: Migration, settings: AtlasSettings) -> str:
    """Render placeholder fields against canonical Atlas identifiers."""
    return migration.sql_path.read_text(encoding="utf-8").format(
        project_id=settings.gcp.project_id,
        dataset_id=settings.gcp.dataset_id,
        location=settings.gcp.location,
    )


def _ledger_fqn(settings: AtlasSettings) -> str:
    return f"{settings.gcp.project_id}.atlas_ops.schema_migrations"


def ensure_ledger(client: bigquery.Client, settings: AtlasSettings) -> None:
    """Create the atlas_ops schema and migration ledger when missing."""
    ddl = _LEDGER_DDL.format(project_id=settings.gcp.project_id, location=settings.gcp.location)
    for statement in ddl.split(";"):
        if statement.strip():
            client.query(statement).result()


def recorded_migrations(client: bigquery.Client, settings: AtlasSettings) -> dict[str, dict[str, Any]]:
    """Return the latest ledger row per migration_id, or {} when no ledger exists."""
    query = f"""
        SELECT migration_id, migration_checksum, status
        FROM `{_ledger_fqn(settings)}`
        QUALIFY ROW_NUMBER() OVER (PARTITION BY migration_id ORDER BY applied_at DESC) = 1
    """
    try:
        rows = list(client.query(query).result())
    except Exception:  # noqa: BLE001 - ledger absent on first run
        return {}
    return {row["migration_id"]: dict(row.items()) for row in rows}


def plan_migrations(
    settings: AtlasSettings | None = None,
    *,
    client: bigquery.Client | None = None,
    manifest_path: Path | None = None,
) -> list[MigrationPlanEntry]:
    """Compute the action for every manifest migration without mutating anything."""
    settings = settings or load_settings()
    bq = client or labeled_bigquery_client(settings.gcp.project_id, "migration")
    recorded = recorded_migrations(bq, settings)
    plan: list[MigrationPlanEntry] = []
    for migration in load_manifest(manifest_path):
        row = recorded.get(migration.migration_id)
        if row is None:
            state = "PENDING"
        elif row["status"] != "APPLIED":
            # A migration that never succeeded is retryable, including with
            # corrected file content: immutability protects applied schema
            # changes, not broken attempts (Sprint 5 fix, regression-tested).
            state = "FAILED_PREVIOUSLY"
        elif row["migration_checksum"] != migration.checksum:
            state = "CHECKSUM_MISMATCH"
        else:
            state = "APPLIED"
        plan.append(
            MigrationPlanEntry(migration_id=migration.migration_id, checksum=migration.checksum, state=state)
        )
    return plan


def _record_ledger_row(
    client: bigquery.Client,
    settings: AtlasSettings,
    migration: Migration,
    status: str,
    error_summary: str | None,
) -> None:
    query = f"""
        MERGE `{_ledger_fqn(settings)}` AS target
        USING (
          SELECT
            @migration_id AS migration_id,
            @migration_checksum AS migration_checksum,
            @git_sha AS git_sha,
            CURRENT_TIMESTAMP() AS applied_at,
            @workflow_run_id AS workflow_run_id,
            @applied_by AS applied_by,
            @status AS status,
            @error_summary AS error_summary
        ) AS source
        ON target.migration_id = source.migration_id
        WHEN MATCHED THEN UPDATE SET
          migration_checksum = source.migration_checksum,
          git_sha = source.git_sha,
          applied_at = source.applied_at,
          workflow_run_id = source.workflow_run_id,
          applied_by = source.applied_by,
          status = source.status,
          error_summary = source.error_summary
        WHEN NOT MATCHED THEN INSERT (
          migration_id, migration_checksum, git_sha, applied_at,
          workflow_run_id, applied_by, status, error_summary
        ) VALUES (
          source.migration_id, source.migration_checksum, source.git_sha, source.applied_at,
          source.workflow_run_id, source.applied_by, source.status, source.error_summary
        )
    """
    params = {
        "migration_id": migration.migration_id,
        "migration_checksum": migration.checksum,
        "git_sha": os.environ.get("ATLAS_DEPLOYED_GIT_SHA") or os.environ.get("GITHUB_SHA"),
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "applied_by": os.environ.get("GITHUB_ACTOR") or os.environ.get("USER"),
        "status": status,
        "error_summary": sanitize_error_message(error_summary, max_length=500),
    }
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter(name, "STRING", value) for name, value in params.items()
        ]
    )
    client.query(query, job_config=job_config).result()


def apply_migrations(
    settings: AtlasSettings | None = None,
    *,
    client: bigquery.Client | None = None,
    manifest_path: Path | None = None,
) -> list[MigrationPlanEntry]:
    """Apply pending migrations in manifest order, recording each in the ledger.

    Raises RuntimeError on the first checksum mismatch or execution failure so a
    failed migration blocks runtime promotion.
    """
    settings = settings or load_settings()
    bq = client or labeled_bigquery_client(settings.gcp.project_id, "migration")
    ensure_ledger(bq, settings)
    results: list[MigrationPlanEntry] = []
    recorded = recorded_migrations(bq, settings)
    for migration in load_manifest(manifest_path):
        row = recorded.get(migration.migration_id)
        if row is not None and row["status"] == "APPLIED" and row["migration_checksum"] != migration.checksum:
            # Only successfully applied migrations are immutable; a FAILED
            # attempt may be retried with corrected content (Sprint 5 fix).
            raise RuntimeError(
                f"Migration {migration.migration_id} content changed after being recorded "
                f"(ledger {row['migration_checksum'][:12]}…, file {migration.checksum[:12]}…). "
                "Shipped migrations are immutable; add a new migration instead."
            )
        if row is not None and row["status"] == "APPLIED":
            results.append(MigrationPlanEntry(migration.migration_id, migration.checksum, "APPLIED"))
            continue
        rendered = render_migration_sql(migration, settings)
        try:
            for statement in rendered.split(";"):
                if statement.strip():
                    bq.query(statement).result()
        except Exception as exc:
            _record_ledger_row(bq, settings, migration, "FAILED", str(exc))
            raise RuntimeError(
                f"Migration {migration.migration_id} failed and was recorded as FAILED: "
                f"{sanitize_error_message(str(exc), max_length=200)}"
            ) from exc
        _record_ledger_row(bq, settings, migration, "APPLIED", None)
        results.append(MigrationPlanEntry(migration.migration_id, migration.checksum, "APPLIED_NOW"))
    return results


def migration_status(
    settings: AtlasSettings | None = None,
    *,
    client: bigquery.Client | None = None,
) -> list[dict[str, Any]]:
    """Return all ledger rows ordered by applied_at."""
    settings = settings or load_settings()
    bq = client or labeled_bigquery_client(settings.gcp.project_id, "migration")
    query = f"SELECT * FROM `{_ledger_fqn(settings)}` ORDER BY applied_at"
    try:
        rows = list(bq.query(query).result())
    except Exception:  # noqa: BLE001 - ledger absent
        return []
    out = []
    for row in rows:
        item = dict(row.items())
        for key, value in item.items():
            if isinstance(value, datetime):
                item[key] = value.astimezone(UTC).isoformat()
        out.append(item)
    return out
