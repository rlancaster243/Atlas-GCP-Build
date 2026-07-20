"""Cloud Storage ingestion for Project Atlas.

Purpose:
    Upload generated JSONL files to immutable, run-scoped GCS object paths.

Interactions:
    Reads local JSONL from the generator and writes objects consumed by the
    BigQuery loader. Uses ``google.cloud.storage`` when credentials exist.

Engineering principles:
    - History is never overwritten: each run writes a unique object key.
    - Idempotent upload checks for an existing object before writing.

Common failure modes:
    - Bucket does not exist or caller lacks ``storage.objects.create``.
    - Attempting to overwrite an existing run object.

Implementation choice:
    Run-scoped keys ``raw/event_date=YYYY-MM-DD/batch_id=<id>/events.jsonl`` extend
    the Sprint 1 folder format without sacrificing immutability. Alternatives
    considered: date-only keys (overwrite risk) and version IDs (harder to audit).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import google.cloud.storage as storage

from atlas.config.settings import AtlasSettings


@dataclass(frozen=True)
class UploadResult:
    """Summary of a GCS upload."""

    gcs_uri: str
    object_name: str
    bytes_uploaded: int
    already_exists: bool
    checksum_sha256: str | None = None


def build_object_name(
    settings: AtlasSettings,
    event_date: str,
    identifier: str,
    *,
    use_batch_id: bool = False,
) -> str:
    """Build the immutable GCS object key for a pipeline run or batch."""
    key_name = "batch_id" if use_batch_id else "run_id"
    return f"{settings.ingestion.gcs_prefix}/event_date={event_date}/{key_name}={identifier}/events.jsonl"


def build_gcs_uri(settings: AtlasSettings, object_name: str) -> str:
    """Build a gs:// URI for an object key."""
    return f"gs://{settings.gcp.bucket_name}/{object_name}"


def upload_events_file(
    settings: AtlasSettings,
    local_path: Path,
    event_date: str,
    run_id: str,
    *,
    client: storage.Client | None = None,
    batch_id: str | None = None,
    expected_checksum: str | None = None,
    fail_once: bool = False,
) -> UploadResult:
    """Upload a local JSONL file to Cloud Storage without overwriting history."""
    if fail_once:
        raise RuntimeError("Injected transient upload failure for retry testing")

    use_batch = batch_id is not None
    identifier = batch_id if batch_id is not None else run_id
    object_name = build_object_name(settings, event_date, identifier, use_batch_id=use_batch)
    gcs_uri = build_gcs_uri(settings, object_name)
    storage_client = client or storage.Client(project=settings.gcp.project_id)
    bucket = storage_client.bucket(settings.gcp.bucket_name)
    blob = bucket.blob(object_name)

    if blob.exists():
        metadata = blob.metadata or {}
        existing_checksum = metadata.get("checksum_sha256")
        if expected_checksum and existing_checksum and existing_checksum != expected_checksum:
            raise ValueError(
                f"Existing GCS object checksum mismatch for {gcs_uri}: "
                f"{existing_checksum} != {expected_checksum}"
            )
        return UploadResult(
            gcs_uri=gcs_uri,
            object_name=object_name,
            bytes_uploaded=blob.size or 0,
            already_exists=True,
            checksum_sha256=existing_checksum,
        )

    blob.metadata = {}
    if expected_checksum:
        blob.metadata["checksum_sha256"] = expected_checksum
    blob.metadata["pipeline_run_id"] = run_id
    if batch_id:
        blob.metadata["batch_id"] = batch_id
    blob.upload_from_filename(local_path, content_type="application/jsonl")
    return UploadResult(
        gcs_uri=gcs_uri,
        object_name=object_name,
        bytes_uploaded=local_path.stat().st_size,
        already_exists=False,
        checksum_sha256=expected_checksum,
    )
