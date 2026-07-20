"""Classification tests for atlas.observability.schema_drift (Sprint 5 P9)."""

from __future__ import annotations

from atlas.observability.schema_drift import compare_table, load_manifest, summarize

EXPECTED = {
    "partition_column": "event_date",
    "columns": {
        "event_id": {"data_type": "STRING", "is_nullable": "NO"},
        "event_date": {"data_type": "DATE", "is_nullable": "NO"},
        "amount": {"data_type": "FLOAT64", "is_nullable": "YES"},
    },
}


def _live(**overrides):
    base = {
        "event_id": {"data_type": "STRING", "is_nullable": "NO", "is_partitioning_column": "NO"},
        "event_date": {"data_type": "DATE", "is_nullable": "NO", "is_partitioning_column": "YES"},
        "amount": {"data_type": "FLOAT64", "is_nullable": "YES", "is_partitioning_column": "NO"},
    }
    base.update(overrides)
    return base


def test_identical_schema_has_no_findings() -> None:
    assert compare_table("ds.t", EXPECTED, _live()) == []


def test_missing_table_is_breaking() -> None:
    findings = compare_table("ds.t", EXPECTED, None)
    assert [f.classification for f in findings] == ["BREAKING"]
    assert findings[0].kind == "missing_table"


def test_removed_field_is_breaking() -> None:
    live = _live()
    del live["amount"]
    findings = compare_table("ds.t", EXPECTED, live)
    assert any(f.kind == "removed_field" and f.classification == "BREAKING" for f in findings)


def test_type_change_is_breaking() -> None:
    live = _live(amount={"data_type": "STRING", "is_nullable": "YES", "is_partitioning_column": "NO"})
    findings = compare_table("ds.t", EXPECTED, live)
    assert any(f.kind == "type_change" and f.classification == "BREAKING" for f in findings)


def test_required_made_nullable_is_breaking() -> None:
    live = _live(event_id={"data_type": "STRING", "is_nullable": "YES", "is_partitioning_column": "NO"})
    findings = compare_table("ds.t", EXPECTED, live)
    assert any(f.kind == "required_made_nullable" and f.classification == "BREAKING" for f in findings)


def test_partition_change_is_breaking() -> None:
    live = _live(event_date={"data_type": "DATE", "is_nullable": "NO", "is_partitioning_column": "NO"})
    findings = compare_table("ds.t", EXPECTED, live)
    assert any(f.kind == "partition_change" and f.classification == "BREAKING" for f in findings)


def test_unapproved_nullable_field_is_warning() -> None:
    live = _live(new_col={"data_type": "STRING", "is_nullable": "YES", "is_partitioning_column": "NO"})
    findings = compare_table("ds.t", EXPECTED, live)
    assert [f.classification for f in findings] == ["WARNING"]
    assert findings[0].kind == "unapproved_new_field"


def test_approved_new_field_is_allowed() -> None:
    live = _live(new_col={"data_type": "STRING", "is_nullable": "YES", "is_partitioning_column": "NO"})
    findings = compare_table("ds.t", EXPECTED, live, allowed_new_fields=["ds.t.new_col"])
    assert [f.classification for f in findings] == ["ALLOWED"]


def test_new_required_field_is_breaking() -> None:
    live = _live(new_req={"data_type": "STRING", "is_nullable": "NO", "is_partitioning_column": "NO"})
    findings = compare_table("ds.t", EXPECTED, live)
    assert [f.classification for f in findings] == ["BREAKING"]
    assert findings[0].kind == "unapproved_required_field"


def test_summarize_counts_by_classification() -> None:
    live = _live(
        new_col={"data_type": "STRING", "is_nullable": "YES", "is_partitioning_column": "NO"},
        event_id={"data_type": "INT64", "is_nullable": "NO", "is_partitioning_column": "NO"},
    )
    counts = summarize(compare_table("ds.t", EXPECTED, live))
    assert counts == {"ALLOWED": 0, "WARNING": 1, "BREAKING": 1}


def test_shipped_manifest_covers_governed_tables() -> None:
    manifest = load_manifest()
    tables = set(manifest["tables"])
    required = {
        "atlas_raw.events",
        "atlas_core.fct_events",
        "atlas_ops.pipeline_runs",
        "atlas_ops.deployments",
        "atlas_ops.task_events",
        "atlas_ops.quality_results",
        "atlas_ops.monitor_evaluations",
    }
    assert required <= tables
