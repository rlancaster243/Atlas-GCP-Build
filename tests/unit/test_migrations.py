"""Unit tests for the ledger-driven migration system (Sprint 4 Phase 9)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from atlas.config.settings import load_settings
from atlas.ops.migrations import (
    Migration,
    apply_migrations,
    load_manifest,
    plan_migrations,
    render_migration_sql,
)


class FakeJob:
    def __init__(self, rows: list[dict[str, Any]] | Exception) -> None:
        self._rows = rows

    def result(self) -> list[Any]:
        if isinstance(self._rows, Exception):
            raise self._rows

        class Row(dict):
            def items(self):  # noqa: ANN202
                return dict.items(self)

            def __getitem__(self, key):  # noqa: ANN001, ANN204
                return dict.__getitem__(self, key)

        return [Row(r) for r in self._rows]


class FakeClient:
    """Scripted BigQuery client: ledger reads return preset rows, DDL succeeds."""

    def __init__(
        self,
        ledger_rows: list[dict[str, Any]] | None = None,
        fail_sql_containing: str | None = None,
    ) -> None:
        self.ledger_rows = ledger_rows or []
        self.fail_sql_containing = fail_sql_containing
        self.executed: list[str] = []

    def query(self, sql: str, job_config: Any = None) -> FakeJob:
        self.executed.append(sql)
        if self.fail_sql_containing and self.fail_sql_containing in sql:
            return FakeJob(RuntimeError("synthetic failure"))
        if "FROM" in sql and "schema_migrations" in sql and "MERGE" not in sql:
            return FakeJob(self.ledger_rows)
        return FakeJob([])


def _write_manifest(tmp_path: Path, entries: list[tuple[str, str, str]]) -> Path:
    """entries: (migration_id, filename, sql content)."""
    manifest_dir = tmp_path / "migrations"
    manifest_dir.mkdir()
    lines = []
    for migration_id, filename, content in entries:
        (tmp_path / filename).write_text(content, encoding="utf-8")
        lines.append(f"{migration_id}|../{filename}")
    manifest = manifest_dir / "manifest.txt"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def test_load_manifest_orders_and_checksums(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path,
        [("001_a", "a.sql", "SELECT 1"), ("002_b", "b.sql", "SELECT 2")],
    )
    migrations = load_manifest(manifest)
    assert [m.migration_id for m in migrations] == ["001_a", "002_b"]
    assert migrations[0].checksum == hashlib.sha256(b"SELECT 1").hexdigest()


def test_load_manifest_rejects_duplicates(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path,
        [("001_a", "a.sql", "SELECT 1"), ("001_a", "b.sql", "SELECT 2")],
    )
    with pytest.raises(ValueError, match="Duplicate migration id"):
        load_manifest(manifest)


def test_load_manifest_rejects_missing_file(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "migrations"
    manifest_dir.mkdir()
    manifest = manifest_dir / "manifest.txt"
    manifest.write_text("001_a|../missing.sql\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        load_manifest(manifest)


def test_load_manifest_rejects_malformed_line(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "migrations"
    manifest_dir.mkdir()
    manifest = manifest_dir / "manifest.txt"
    manifest.write_text("001_a_no_pipe\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Malformed manifest line"):
        load_manifest(manifest)


def test_shipped_manifest_parses_and_is_additive() -> None:
    migrations = load_manifest()
    assert [m.migration_id for m in migrations][:2] == [
        "001_create_pipeline_runs_table",
        "002_sprint3_raw_batch_columns",
    ]
    settings = load_settings()
    for migration in migrations:
        sql = render_migration_sql(migration, settings).upper()
        assert "DROP TABLE" not in sql
        assert "DELETE FROM" not in sql
        assert "TRUNCATE" not in sql


def test_plan_reports_pending_applied_and_mismatch(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path,
        [
            ("001_a", "a.sql", "SELECT 1"),
            ("002_b", "b.sql", "SELECT 2"),
            ("003_c", "c.sql", "SELECT 3"),
        ],
    )
    checksum_a = hashlib.sha256(b"SELECT 1").hexdigest()
    client = FakeClient(
        ledger_rows=[
            {"migration_id": "001_a", "migration_checksum": checksum_a, "status": "APPLIED"},
            {"migration_id": "002_b", "migration_checksum": "tampered", "status": "APPLIED"},
        ]
    )
    plan = plan_migrations(load_settings(), client=client, manifest_path=manifest)
    states = {e.migration_id: e.state for e in plan}
    assert states == {"001_a": "APPLIED", "002_b": "CHECKSUM_MISMATCH", "003_c": "PENDING"}


def test_apply_refuses_changed_recorded_migration(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, [("001_a", "a.sql", "SELECT 1 -- edited")])
    client = FakeClient(
        ledger_rows=[{"migration_id": "001_a", "migration_checksum": "original", "status": "APPLIED"}]
    )
    with pytest.raises(RuntimeError, match="content changed"):
        apply_migrations(load_settings(), client=client, manifest_path=manifest)


def test_failed_migration_with_corrected_content_is_retryable(tmp_path: Path) -> None:
    # Regression (Sprint 5): a FAILED attempt is not immutable — the corrected
    # file must plan as FAILED_PREVIOUSLY and re-apply, not CHECKSUM_MISMATCH.
    manifest = _write_manifest(tmp_path, [("001_a", "a.sql", "SELECT 1 -- fixed")])
    client = FakeClient(
        ledger_rows=[{"migration_id": "001_a", "migration_checksum": "broken-original", "status": "FAILED"}]
    )
    plan = plan_migrations(load_settings(), client=client, manifest_path=manifest)
    assert plan[0].state == "FAILED_PREVIOUSLY"
    results = apply_migrations(load_settings(), client=client, manifest_path=manifest)
    assert [r.state for r in results] == ["APPLIED_NOW"]


def test_apply_skips_recorded_migrations_idempotently(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, [("001_a", "a.sql", "SELECT 1")])
    checksum = hashlib.sha256(b"SELECT 1").hexdigest()
    client = FakeClient(
        ledger_rows=[{"migration_id": "001_a", "migration_checksum": checksum, "status": "APPLIED"}]
    )
    results = apply_migrations(load_settings(), client=client, manifest_path=manifest)
    assert [r.state for r in results] == ["APPLIED"]
    assert not any("SELECT 1" in sql for sql in client.executed if "MERGE" not in sql and "CREATE" not in sql)


def test_apply_records_failure_and_blocks(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, [("001_bad", "bad.sql", "SELECT boom_marker")])
    client = FakeClient(fail_sql_containing="boom_marker")
    with pytest.raises(RuntimeError, match="001_bad failed"):
        apply_migrations(load_settings(), client=client, manifest_path=manifest)
    merges = [sql for sql in client.executed if "MERGE" in sql]
    assert merges, "failed migration must still be recorded in the ledger"


def test_apply_retry_after_failure_reruns_migration(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, [("001_a", "a.sql", "SELECT 1")])
    checksum = hashlib.sha256(b"SELECT 1").hexdigest()
    client = FakeClient(
        ledger_rows=[{"migration_id": "001_a", "migration_checksum": checksum, "status": "FAILED"}]
    )
    results = apply_migrations(load_settings(), client=client, manifest_path=manifest)
    assert [r.state for r in results] == ["APPLIED_NOW"]


def test_render_migration_sql_parameterizes_dataset(tmp_path: Path) -> None:
    sql_file = tmp_path / "m.sql"
    sql_file.write_text("ALTER TABLE `{project_id}.{dataset_id}.events` ADD COLUMN x STRING", "utf-8")
    migration = Migration("001_x", sql_file, "abc")
    settings = load_settings()
    rendered = render_migration_sql(migration, settings)
    assert settings.gcp.project_id in rendered
    assert settings.gcp.dataset_id in rendered
    assert "{" not in rendered
