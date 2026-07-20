"""Structured pipeline logging for Project Atlas.

Purpose:
    Emit consistent, machine-readable logs for every pipeline step.

Interactions:
    Called by generator, upload, loader, validation, and orchestrator.
    Writes JSON lines to ``logs/<pipeline_run_id>.jsonl``.

Engineering principles:
    - Observability without external monitoring in Sprint 1.
    - Every log record includes run identity and source file for recovery.

Common failure modes:
    - Missing log directory permissions in Cloud Shell.
    - Duplicate handlers if ``configure_logging`` is called repeatedly.

Implementation choice:
    Standard library logging with a JSON formatter keeps dependencies minimal.
    Alternatives considered: structlog (extra dependency) and print-based logs
    (insufficient for automated acceptance tests).
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal


class JsonLogFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in (
            "pipeline_run_id",
            "step",
            "status",
            "duration_ms",
            "rows_processed",
            "source_file",
            "details",
        ):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, default=str)


def configure_logging(log_dir: Path, pipeline_run_id: str) -> logging.Logger:
    """Configure root Atlas logger with console and file handlers."""
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("atlas")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    formatter = JsonLogFormatter()
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(log_dir / f"{pipeline_run_id}.jsonl")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


def new_pipeline_run_id(prefix: str = "atlas") -> str:
    """Create a unique pipeline run identifier."""
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{timestamp}-{uuid.uuid4().hex[:8]}"


@dataclass
class StepLogger:
    """Context manager that logs step start, success, and failure."""

    logger: logging.Logger
    pipeline_run_id: str
    step: str
    source_file: str | None = None
    rows_processed: int | None = None
    details: dict[str, Any] = field(default_factory=dict)
    _started_at: float = field(default=0.0, init=False)

    def __enter__(self) -> StepLogger:
        self._started_at = time.perf_counter()
        self._log("STARTED", rows_processed=self.rows_processed)
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> Literal[False]:
        duration_ms = int((time.perf_counter() - self._started_at) * 1000)
        if exc_type is None:
            self._log("SUCCEEDED", duration_ms=duration_ms, rows_processed=self.rows_processed)
            return False
        self.details["error"] = str(exc)
        self._log("FAILED", duration_ms=duration_ms, rows_processed=self.rows_processed)
        return False

    def _log(
        self,
        status: str,
        duration_ms: int | None = None,
        rows_processed: int | None = None,
    ) -> None:
        extra = {
            "pipeline_run_id": self.pipeline_run_id,
            "step": self.step,
            "status": status,
            "source_file": self.source_file,
            "rows_processed": rows_processed,
            "details": self.details,
        }
        if duration_ms is not None:
            extra["duration_ms"] = duration_ms
        self.logger.info(f"{self.step} {status.lower()}", extra=extra)
