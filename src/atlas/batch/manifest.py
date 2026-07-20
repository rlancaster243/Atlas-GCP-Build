"""Artifact manifest helpers for idempotent batch generation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class BatchManifest:
    """Checksum metadata for one generated batch artifact."""

    batch_id: str
    processing_date: str
    pipeline_run_id: str
    seed: int
    row_count: int
    checksum_sha256: str
    output_path: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def compute_file_checksum(path: Path) -> str:
    """Return the SHA-256 digest for a local file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(path: Path, manifest: BatchManifest) -> None:
    """Write a batch manifest JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")


def read_manifest(path: Path) -> BatchManifest | None:
    """Read a batch manifest when present."""
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return BatchManifest(**payload)


def manifests_match(existing: BatchManifest, requested: BatchManifest) -> bool:
    """Return True when an existing artifact matches the requested batch identity."""
    return (
        existing.batch_id == requested.batch_id
        and existing.processing_date == requested.processing_date
        and existing.seed == requested.seed
        and existing.row_count == requested.row_count
        and existing.checksum_sha256 == requested.checksum_sha256
    )
