"""Unit tests for batch manifest checksum helpers."""

from __future__ import annotations

from pathlib import Path

from atlas.batch.manifest import (
    BatchManifest,
    compute_file_checksum,
    manifests_match,
    read_manifest,
    write_manifest,
)


def test_manifest_round_trip(tmp_path: Path) -> None:
    file_path = tmp_path / "events.jsonl"
    file_path.write_text('{"event_id":"1"}\n', encoding="utf-8")
    checksum = compute_file_checksum(file_path)
    manifest = BatchManifest(
        batch_id="atlas-20260715",
        processing_date="2026-07-15",
        pipeline_run_id="run-1",
        seed=42,
        row_count=1,
        checksum_sha256=checksum,
        output_path=str(file_path),
    )
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path, manifest)
    loaded = read_manifest(manifest_path)
    assert loaded is not None
    assert manifests_match(loaded, manifest)
