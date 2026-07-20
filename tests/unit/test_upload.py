"""Unit tests for GCS object naming and upload idempotency."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from atlas.config.settings import load_settings
from atlas.ingestion.upload import build_object_name, upload_events_file


def test_build_object_name_supports_run_id_and_batch_id() -> None:
    settings = load_settings()
    run_path = build_object_name(settings, "2026-07-14", "atlas-run-123")
    batch_path = build_object_name(settings, "2026-07-14", "atlas-20260714", use_batch_id=True)
    assert run_path == "raw/event_date=2026-07-14/run_id=atlas-run-123/events.jsonl"
    assert batch_path == "raw/event_date=2026-07-14/batch_id=atlas-20260714/events.jsonl"


def test_upload_skips_existing_object(tmp_path: Path) -> None:
    settings = load_settings()
    local_path = tmp_path / "events.jsonl"
    local_path.write_text('{"event_id":"1"}\n', encoding="utf-8")

    blob = MagicMock()
    blob.exists.return_value = True
    blob.size = 42
    bucket = MagicMock()
    bucket.blob.return_value = blob
    client = MagicMock()
    client.bucket.return_value = bucket

    result = upload_events_file(
        settings,
        local_path,
        "2026-07-14",
        "atlas-run-123",
        client=client,
    )
    assert result.already_exists is True
    blob.upload_from_filename.assert_not_called()
