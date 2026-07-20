"""Structured logging contract for Project Atlas (Sprint 5, ADR-011).

One JSON-per-line contract for every Atlas structured event, across the step
runner, Airflow callbacks, deployment scripts, and the observability monitor.
Events go to stdout so Composer/Airflow routes them into task logs and, via
the Atlas log sink, into the dedicated log bucket.

Contract guarantees (tested in tests/unit/test_observability_logging.py):
- deterministic field names drawn from a fixed allowlist,
- controlled severity and event vocabulary,
- UTC ISO-8601 timestamps,
- centralized error sanitization and truncation (reuses the audited
  sanitizer from atlas.ops.audit),
- non-serializable values degrade to strings instead of raising,
- emission failures never propagate into the caller's data path.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import UTC, datetime
from typing import Any, TextIO

from atlas.ops.audit import sanitize_error_message

# Stable envelope marker so log filters can select Atlas contract events
# without matching unrelated JSON output.
EVENT_MARKER = "atlas_event"

ALLOWED_SEVERITIES = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})

# Correlation hierarchy (ADR-011):
# deployment_id -> airflow_run_id -> pipeline_run_id -> batch_id -> task_id -> attempt_number
CORRELATION_FIELDS = (
    "deployment_id",
    "airflow_run_id",
    "pipeline_run_id",
    "batch_id",
    "task_id",
    "attempt_number",
)

# Full field allowlist. Anything not listed here is rejected in strict mode
# and dropped (with a contract_violation note) otherwise.
ALLOWED_FIELDS = frozenset(
    {
        "timestamp",
        "severity",
        "event_type",
        "component",
        "environment",
        "git_sha",
        "dag_id",
        "processing_date",
        "status",
        "duration_ms",
        "rows_generated",
        "rows_loaded",
        "rows_accepted",
        "rows_rejected",
        "fact_rows",
        "mart_event_count",
        "check_name",
        "check_category",
        "observed_value",
        "threshold",
        "expected_value",
        "error_type",
        "error_message",
        "correlation_id",
        "message",
        "details",
        *CORRELATION_FIELDS,
    }
)

_INT_FIELDS = frozenset(
    {
        "attempt_number",
        "duration_ms",
        "rows_generated",
        "rows_loaded",
        "rows_accepted",
        "rows_rejected",
        "fact_rows",
        "mart_event_count",
    }
)

_MAX_ERROR_LENGTH = 2000
_MAX_DETAILS_LENGTH = 4000

# Direct Cloud Logging emission (Sprint 5 live-acceptance mitigation).
# Composer 3 build.13 was observed not exporting any Airflow component logs
# to the customer project (documented in the Sprint 5 incident/validation
# reports), which silently strands stdout-only telemetry. When this env var
# is "true", contract events are ALSO written straight to the Cloud Logging
# API under logName atlas-events, where the Atlas sink filter
# (jsonPayload.atlas_event=true) routes them to the atlas-observability
# bucket. Off by default: local runs, unit tests, and CI stay offline.
CLOUD_EMIT_ENV_VAR = "ATLAS_LOG_TO_CLOUD_LOGGING"
CLOUD_LOG_NAME = "atlas-events"

_SEVERITY_RANK = {"DEBUG": 100, "INFO": 200, "WARNING": 400, "ERROR": 500, "CRITICAL": 600}

_cloud_logger: Any = None
_cloud_logger_failed = False


def _get_cloud_logger() -> Any:
    """Lazily build (and cache) a Cloud Logging logger; never raises."""
    global _cloud_logger, _cloud_logger_failed
    if _cloud_logger is not None or _cloud_logger_failed:
        return _cloud_logger
    try:
        import google.cloud.logging as gcloud_logging

        _cloud_logger = gcloud_logging.Client().logger(CLOUD_LOG_NAME)
    except Exception:  # noqa: BLE001 - degraded telemetry must not break callers
        _cloud_logger_failed = True
    return _cloud_logger


def _emit_to_cloud(event: dict[str, Any]) -> None:
    """Best-effort direct write of one contract event to Cloud Logging."""
    logger = _get_cloud_logger()
    if logger is None:
        return
    try:
        logger.log_struct(event, severity=event.get("severity", "INFO"))
    except Exception:  # noqa: BLE001, S110 - fallback path; stdout copy already exists
        pass


class ContractViolation(ValueError):
    """Raised in strict mode when an event violates the logging contract."""


def _coerce(value: Any) -> Any:
    """Return a JSON-serializable representation without raising."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, dict):
        return {str(k): _coerce(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_coerce(v) for v in value]
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return repr(value)[:500]


def build_event(
    event_type: str,
    *,
    severity: str = "INFO",
    strict: bool = False,
    **fields: Any,
) -> dict[str, Any]:
    """Build a contract-conformant event dict.

    In strict mode unknown fields or invalid severities raise
    ContractViolation; otherwise they are dropped/normalized and noted under
    ``contract_violations`` so telemetry bugs stay visible without breaking
    the caller.
    """
    if not event_type or not isinstance(event_type, str):
        raise ContractViolation("event_type is required")
    severity = severity.upper()
    violations: list[str] = []
    if severity not in ALLOWED_SEVERITIES:
        if strict:
            raise ContractViolation(f"invalid severity: {severity}")
        violations.append(f"severity:{severity}")
        severity = "INFO"

    event: dict[str, Any] = {
        EVENT_MARKER: True,
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "severity": severity,
        "event_type": event_type,
    }

    for key, value in fields.items():
        if value is None:
            continue
        if key not in ALLOWED_FIELDS:
            if strict:
                raise ContractViolation(f"field not in contract: {key}")
            violations.append(f"field:{key}")
            continue
        if key in _INT_FIELDS:
            try:
                value = int(value)
            except (TypeError, ValueError):
                violations.append(f"type:{key}")
                continue
        if key == "error_message":
            value = sanitize_error_message(str(value), max_length=_MAX_ERROR_LENGTH)
        if key == "details":
            value = _coerce(value)
            rendered = json.dumps(value, default=str)
            if len(rendered) > _MAX_DETAILS_LENGTH:
                value = {"truncated": True, "preview": rendered[:_MAX_DETAILS_LENGTH]}
        event[key] = _coerce(value)

    if violations:
        event["contract_violations"] = violations
    return event


def emit_event(
    event_type: str,
    *,
    severity: str = "INFO",
    stream: TextIO | None = None,
    strict: bool = False,
    **fields: Any,
) -> dict[str, Any] | None:
    """Build and print one structured event line; never raises in non-strict mode.

    Returns the event dict (useful for tests) or None when emission failed
    and a fallback error line was printed instead.
    """
    out = stream if stream is not None else sys.stdout
    try:
        event = build_event(event_type, severity=severity, strict=strict, **fields)
        print(json.dumps(event, default=str), file=out, flush=True)
        if os.environ.get(CLOUD_EMIT_ENV_VAR, "").lower() == "true":
            _emit_to_cloud(event)
        return event
    except ContractViolation:
        raise
    except Exception as exc:  # noqa: BLE001 - telemetry must not break the data path
        fallback = {
            EVENT_MARKER: True,
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "severity": "ERROR",
            "event_type": "telemetry_emit_failed",
            "error_type": type(exc).__name__,
            "error_message": sanitize_error_message(str(exc), max_length=_MAX_ERROR_LENGTH),
        }
        try:
            print(json.dumps(fallback, default=str), file=out, flush=True)
        except Exception:  # noqa: BLE001, S110 - last resort: stay silent, never raise
            pass
        return None


def new_correlation_id() -> str:
    """Random identifier linking events emitted by one logical operation."""
    return uuid.uuid4().hex


def correlation_fields_from_context(context: dict[str, Any]) -> dict[str, Any]:
    """Extract the standard correlation identifiers from a run-context dict."""
    return {key: context.get(key) for key in CORRELATION_FIELDS if context.get(key) is not None}
