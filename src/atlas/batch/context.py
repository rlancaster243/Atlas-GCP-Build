"""Stable batch identity and artifact path resolution."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from atlas.config.settings import atlas_root

_BATCH_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


@dataclass(frozen=True)
class BatchContext:
    """Resolved identifiers for one orchestrated batch."""

    processing_date: str
    batch_id: str
    pipeline_run_id: str
    seed: int
    local_file_path: Path
    manifest_path: Path


def validate_batch_id(batch_id: str) -> str:
    """Validate a user-supplied batch identifier."""
    if not _BATCH_ID_PATTERN.fullmatch(batch_id):
        raise ValueError(
            f"batch_id must match ^[a-zA-Z0-9][a-zA-Z0-9._-]{{0,127}}$ but received {batch_id!r}"
        )
    return batch_id


def default_batch_id(processing_date: str) -> str:
    """Return the default scheduled batch identifier."""
    parsed = date.fromisoformat(processing_date)
    return f"atlas-{parsed.strftime('%Y%m%d')}"


def default_seed_for_date(processing_date: str) -> int:
    """Derive a deterministic seed from the processing date."""
    digest = hashlib.sha256(processing_date.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def build_batch_artifact_paths(batch_id: str) -> tuple[Path, Path]:
    """Return local JSONL and manifest paths for a batch."""
    run_dir = atlas_root() / "data" / "runs" / batch_id
    return run_dir / "events.jsonl", run_dir / "manifest.json"


def sanitize_airflow_run_id(airflow_run_id: str) -> str:
    """Convert an Airflow run id into a path-safe suffix."""
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", airflow_run_id).strip("-")[:120]


def build_pipeline_run_id(processing_date: str, airflow_run_id: str) -> str:
    """Build a unique execution identity for one Airflow run."""
    suffix = sanitize_airflow_run_id(airflow_run_id)
    parsed = date.fromisoformat(processing_date)
    return f"atlas-airflow-{parsed.strftime('%Y%m%d')}-{suffix}"


def resolve_batch_context(
    *,
    processing_date: str | None = None,
    batch_id: str | None = None,
    pipeline_run_id: str | None = None,
    seed: int | None = None,
    airflow_run_id: str | None = None,
) -> BatchContext:
    """Resolve batch context from explicit orchestration inputs."""
    if processing_date is None:
        raise ValueError("processing_date is required")
    datetime.strptime(processing_date, "%Y-%m-%d")
    resolved_batch_id = validate_batch_id(batch_id or default_batch_id(processing_date))
    resolved_pipeline_run_id = pipeline_run_id
    if resolved_pipeline_run_id is None:
        if airflow_run_id is None:
            raise ValueError("pipeline_run_id or airflow_run_id is required")
        resolved_pipeline_run_id = build_pipeline_run_id(processing_date, airflow_run_id)
    local_file_path, manifest_path = build_batch_artifact_paths(resolved_batch_id)
    return BatchContext(
        processing_date=processing_date,
        batch_id=resolved_batch_id,
        pipeline_run_id=resolved_pipeline_run_id,
        seed=seed if seed is not None else default_seed_for_date(processing_date),
        local_file_path=local_file_path,
        manifest_path=manifest_path,
    )
