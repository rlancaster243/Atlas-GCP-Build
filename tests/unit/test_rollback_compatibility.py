"""Rollback schema-compatibility decision tests (Sprint 6, ADR-015)."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.ops.migrations import Migration, load_manifest
from atlas.ops.rollback_compatibility import evaluate_rollback_compatibility


def _migration(migration_id: str, breaking: bool = False) -> Migration:
    return Migration(
        migration_id=migration_id,
        sql_path=Path("/dev/null"),
        checksum="0" * 64,
        breaking=breaking,
    )


MANIFEST = [
    _migration("001_base"),
    _migration("002_additive"),
    _migration("003_breaking_type_change", breaking=True),
]


def test_rollback_allowed_when_newer_migrations_are_additive() -> None:
    decision = evaluate_rollback_compatibility(
        applied_migration_ids=["001_base", "002_additive"],
        target_release_migration_ids=["001_base"],
        manifest=MANIFEST,
    )
    assert decision.eligible is True
    assert "additive" in decision.reason


def test_rollback_blocked_across_breaking_migration() -> None:
    """S6-RBK-003: irreversible migration blocks runtime rollback."""
    decision = evaluate_rollback_compatibility(
        applied_migration_ids=["001_base", "002_additive", "003_breaking_type_change"],
        target_release_migration_ids=["001_base", "002_additive"],
        manifest=MANIFEST,
    )
    assert decision.eligible is False
    assert decision.blocking_migrations == ("003_breaking_type_change",)
    assert "recover forward" in decision.reason
    assert "never reversed automatically" in decision.reason


def test_target_knowing_breaking_migration_is_eligible() -> None:
    """A release built after the breaking migration may still be a target."""
    decision = evaluate_rollback_compatibility(
        applied_migration_ids=["001_base", "002_additive", "003_breaking_type_change"],
        target_release_migration_ids=["001_base", "002_additive", "003_breaking_type_change"],
        manifest=MANIFEST,
    )
    assert decision.eligible is True


def test_unclassifiable_applied_migration_refuses_rollback() -> None:
    """Unknown applied migrations are refused rather than guessed compatible."""
    decision = evaluate_rollback_compatibility(
        applied_migration_ids=["001_base", "999_mystery"],
        target_release_migration_ids=["001_base"],
        manifest=MANIFEST,
    )
    assert decision.eligible is False
    assert "cannot be classified" in decision.reason


def test_manifest_parses_breaking_flag(tmp_path: Path) -> None:
    sql = tmp_path / "001.sql"
    sql.write_text("SELECT 1")
    manifest = tmp_path / "manifest.txt"
    manifest.write_text("001_base|001.sql\n002_breaking|001.sql|breaking\n")
    migrations = load_manifest(manifest)
    assert [m.breaking for m in migrations] == [False, True]


def test_manifest_rejects_unknown_flags(tmp_path: Path) -> None:
    sql = tmp_path / "001.sql"
    sql.write_text("SELECT 1")
    manifest = tmp_path / "manifest.txt"
    manifest.write_text("001_base|001.sql|yolo\n")
    with pytest.raises(ValueError, match="Unknown manifest flags"):
        load_manifest(manifest)
