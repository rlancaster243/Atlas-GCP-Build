"""Cardinality-budget and catalog tests for atlas.observability.metrics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas.observability.metrics import (
    MONITOR_STATUS_VALUES,
    MetricContractError,
    load_catalog,
    publish_gauge_safely,
    validate_point,
)

CATALOG = load_catalog()
CATALOG_PATH = Path(__file__).resolve().parents[2] / "observability" / "metrics" / "metric-descriptors.json"

FORBIDDEN_LABELS = {"pipeline_run_id", "batch_id", "deployment_id", "error_message", "airflow_run_id"}


def test_catalog_loads_and_is_nonempty() -> None:
    assert len(CATALOG) >= 10
    assert all(t.startswith("custom.googleapis.com/atlas/") for t in CATALOG)


def test_no_high_cardinality_labels_in_catalog() -> None:
    for metric_type, spec in CATALOG.items():
        overlap = set(spec["labels"]) & FORBIDDEN_LABELS
        assert not overlap, f"{metric_type} declares forbidden labels {overlap}"


def test_catalog_declares_kind_unit_and_value_type() -> None:
    for spec in CATALOG.values():
        assert spec["metric_kind"] in {"GAUGE", "CUMULATIVE"}
        assert spec["value_type"] in {"INT64", "DOUBLE"}
        assert spec.get("unit")
        assert spec.get("description")


def test_projected_cardinality_within_budget() -> None:
    budget = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["cardinality_budget"]
    max_series = budget["max_projected_time_series"]
    sizes = {
        "environment": 1,
        "dag_id": 2,
        "component": 4,
        "severity": 3,
        "mode": 2,
        "status": 4,
        "check_name": 15,
    }
    projected = 0
    for spec in CATALOG.values():
        series = 1
        for label in spec["labels"]:
            series *= sizes[label]
        projected += series
    assert projected <= max_series, f"projected {projected} series exceeds budget {max_series}"


def test_validate_point_accepts_valid_labels() -> None:
    descriptor = validate_point(
        "custom.googleapis.com/atlas/monitor/check_status",
        {"environment": "atlas-dev", "check_name": "freshness", "mode": "normal"},
        CATALOG,
    )
    assert descriptor["value_type"] == "INT64"


def test_validate_point_rejects_unknown_metric() -> None:
    with pytest.raises(MetricContractError, match="not in catalog"):
        validate_point("custom.googleapis.com/atlas/bogus/metric", {}, CATALOG)


def test_validate_point_rejects_forbidden_label() -> None:
    with pytest.raises(MetricContractError, match="not allowed"):
        validate_point(
            "custom.googleapis.com/atlas/data/rejection_rate",
            {"environment": "atlas-dev", "mode": "normal", "pipeline_run_id": "pr-1"},
            CATALOG,
        )


def test_validate_point_rejects_unbounded_label_value() -> None:
    with pytest.raises(MetricContractError, match="outside bounded set"):
        validate_point(
            "custom.googleapis.com/atlas/data/rejection_rate",
            {"environment": "prod-42", "mode": "normal"},
            CATALOG,
        )


def test_validate_point_requires_all_labels() -> None:
    with pytest.raises(MetricContractError, match="missing required labels"):
        validate_point(
            "custom.googleapis.com/atlas/data/rejection_rate",
            {"environment": "atlas-dev"},
            CATALOG,
        )


def test_drill_mode_is_a_separate_series_not_a_pollutant() -> None:
    # Drill points carry mode=drill so they never mix with normal series.
    for labels_mode in ("normal", "drill"):
        validate_point(
            "custom.googleapis.com/atlas/pipeline/last_success_age_seconds",
            {"environment": "atlas-dev", "dag_id": "atlas_batch_pipeline", "mode": labels_mode},
            CATALOG,
        )


def test_monitor_status_value_mapping_is_stable() -> None:
    assert MONITOR_STATUS_VALUES == {"PASS": 0, "WARN": 1, "FAIL": 2, "NO_DATA": -1, "DISABLED": -2}


def test_publish_gauge_safely_never_raises(capsys) -> None:
    # Contract violation inside safely-wrapper degrades to a structured event.
    ok = publish_gauge_safely(
        "example-gcp-project",
        "custom.googleapis.com/atlas/bogus/metric",
        1,
        {},
        catalog=CATALOG,
    )
    assert ok is False
    assert "metric_publish_failed" in capsys.readouterr().out
