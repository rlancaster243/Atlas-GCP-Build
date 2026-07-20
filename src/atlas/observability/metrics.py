"""Cloud Monitoring metric publication for Atlas (Sprint 5, Phase 6).

Descriptors are declared once in ``observability/metrics/metric-descriptors.json``
(the versioned catalog and cardinality budget) and created idempotently by
``ensure_descriptors``. Publishing validates every point against the catalog:
unknown metric types or labels outside the bounded sets are rejected before
they can create unbudgeted time series.

Telemetry-safety: ``publish_gauge_safely`` never raises; a Monitoring outage
degrades to a structured ``metric_publish_failed`` event (ADR-011).

The google-cloud-monitoring dependency is imported lazily so DAG parsing and
credentialless static validation never require it.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from atlas.observability.logging import emit_event

_CATALOG_PATH = Path(__file__).resolve().parents[3] / "observability" / "metrics" / "metric-descriptors.json"

MONITOR_STATUS_VALUES = {"PASS": 0, "WARN": 1, "FAIL": 2, "NO_DATA": -1, "DISABLED": -2}

_ALLOWED_LABEL_VALUES: dict[str, Any] = {
    "environment": {"atlas-dev"},
    "dag_id": {"atlas_batch_pipeline", "atlas_observability_monitor"},
    "component": {"pipeline", "monitor", "deployment", "cost"},
    "severity": {"INFO", "WARNING", "CRITICAL"},
    "mode": {"normal", "drill"},
    "status": {"SUCCESS", "FAILED", "ROLLED_BACK", "ROLLBACK_FAILED"},
    # check_name is bounded by config/observability.yaml; validated for shape only.
    "check_name": None,
}
_MAX_CHECK_NAME_LENGTH = 64


class MetricContractError(ValueError):
    """Raised when a publish request violates the metric catalog."""


def load_catalog(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Return {metric_type: descriptor} from the versioned catalog."""
    raw = json.loads((path or _CATALOG_PATH).read_text(encoding="utf-8"))
    return {d["type"]: d for d in raw["descriptors"]}


def validate_point(
    metric_type: str,
    labels: dict[str, str],
    catalog: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate one metric point against the catalog; returns the descriptor."""
    catalog = catalog or load_catalog()
    descriptor = catalog.get(metric_type)
    if descriptor is None:
        raise MetricContractError(f"metric not in catalog: {metric_type}")
    allowed_labels = set(descriptor["labels"])
    for key, value in labels.items():
        if key not in allowed_labels:
            raise MetricContractError(f"label {key!r} not allowed on {metric_type}")
        bounded = _ALLOWED_LABEL_VALUES.get(key)
        if bounded is not None and value not in bounded:
            raise MetricContractError(f"label value {key}={value!r} outside bounded set")
        if key == "check_name" and (not value or len(value) > _MAX_CHECK_NAME_LENGTH):
            raise MetricContractError("check_name label must be short and non-empty")
    missing = allowed_labels - set(labels)
    if missing:
        raise MetricContractError(f"missing required labels for {metric_type}: {sorted(missing)}")
    return descriptor


def ensure_descriptors(project_id: str, *, catalog_path: Path | None = None) -> list[str]:
    """Idempotently create catalog descriptors; returns the created types."""
    import google.cloud.monitoring_v3 as monitoring_v3
    from google.api import label_pb2, metric_pb2

    client = monitoring_v3.MetricServiceClient()
    project_name = f"projects/{project_id}"
    existing = {
        d.type
        for d in client.list_metric_descriptors(
            request={
                "name": project_name,
                "filter": 'metric.type = starts_with("custom.googleapis.com/atlas/")',
            }
        )
    }
    created: list[str] = []
    kind_map = {
        "GAUGE": metric_pb2.MetricDescriptor.MetricKind.GAUGE,
        "CUMULATIVE": metric_pb2.MetricDescriptor.MetricKind.CUMULATIVE,
    }
    value_map = {
        "DOUBLE": metric_pb2.MetricDescriptor.ValueType.DOUBLE,
        "INT64": metric_pb2.MetricDescriptor.ValueType.INT64,
    }
    for metric_type, spec in load_catalog(catalog_path).items():
        if metric_type in existing:
            continue
        descriptor = metric_pb2.MetricDescriptor(
            type=metric_type,
            metric_kind=kind_map[spec["metric_kind"]],
            value_type=value_map[spec["value_type"]],
            unit=spec.get("unit", "1"),
            description=spec["description"],
            labels=[
                label_pb2.LabelDescriptor(key=key, value_type=label_pb2.LabelDescriptor.ValueType.STRING)
                for key in spec["labels"]
            ],
        )
        client.create_metric_descriptor(name=project_name, metric_descriptor=descriptor)
        created.append(metric_type)
    return created


def publish_gauge(
    project_id: str,
    metric_type: str,
    value: float | int,
    labels: dict[str, str],
    *,
    catalog: dict[str, dict[str, Any]] | None = None,
) -> None:
    """Write one gauge point after catalog validation."""
    descriptor = validate_point(metric_type, labels, catalog)

    import google.cloud.monitoring_v3 as monitoring_v3

    client = monitoring_v3.MetricServiceClient()
    series = monitoring_v3.TimeSeries()
    series.metric.type = metric_type
    for key, val in labels.items():
        series.metric.labels[key] = val
    series.resource.type = "global"
    series.resource.labels["project_id"] = project_id

    now = time.time()
    interval = monitoring_v3.TimeInterval({"end_time": {"seconds": int(now), "nanos": int((now % 1) * 1e9)}})
    point = monitoring_v3.Point({"interval": interval})
    if descriptor["value_type"] == "INT64":
        point.value.int64_value = int(value)
    else:
        point.value.double_value = float(value)
    series.points = [point]
    client.create_time_series(name=f"projects/{project_id}", time_series=[series])


def publish_gauge_safely(
    project_id: str,
    metric_type: str,
    value: float | int,
    labels: dict[str, str],
    *,
    catalog: dict[str, dict[str, Any]] | None = None,
) -> bool:
    """Publish one point without ever propagating telemetry failure."""
    try:
        publish_gauge(project_id, metric_type, value, labels, catalog=catalog)
        return True
    except Exception as exc:  # noqa: BLE001 - telemetry must not break the caller
        emit_event(
            "metric_publish_failed",
            severity="ERROR",
            component="metrics",
            check_name=labels.get("check_name"),
            error_type=type(exc).__name__,
            error_message=f"{metric_type}: {exc}",
        )
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Atlas metric descriptor management")
    parser.add_argument("--ensure-descriptors", action="store_true")
    parser.add_argument("--project-id", default=None)
    args = parser.parse_args()
    if args.ensure_descriptors:
        from atlas.config.settings import load_settings

        project_id = args.project_id or load_settings().gcp.project_id
        created = ensure_descriptors(project_id)
        print(json.dumps({"created": created, "catalog_size": len(load_catalog())}))
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
