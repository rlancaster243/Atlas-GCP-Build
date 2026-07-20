"""Unit tests for the synthetic event generator."""

from __future__ import annotations

from dataclasses import replace

from atlas.config.settings import load_settings
from atlas.generator.events import EventRecord, generate_events, generate_events_for_batch


def test_event_record_excludes_ingested_at_from_jsonl() -> None:
    record = EventRecord(
        event_id="1",
        user_id="u1",
        event_name="app_open",
        event_timestamp="2026-07-14T12:00:00+00:00",
        event_date="2026-07-14",
        country_code="US",
        platform="web",
        app_version="1.0.0",
    )
    assert "ingested_at" not in record.to_dict()


def test_generate_events_count_and_seed(tmp_path) -> None:
    settings = load_settings()
    settings = replace(
        settings,
        generator=replace(settings.generator, output_dir=tmp_path),
    )
    first = generate_events(settings)
    second = generate_events(settings)
    assert first.event_count == 50000
    assert first.output_path.exists()
    assert first.output_path == second.output_path
    assert first.anomaly_counts["null_user_ids"] == 500
    assert first.anomaly_counts["duplicate_event_ids"] == 50

    first_line = first.output_path.read_text(encoding="utf-8").splitlines()[0]
    assert "ingested_at" not in first_line


def test_generate_events_for_batch_is_deterministic(tmp_path, monkeypatch) -> None:
    settings = load_settings()
    output = tmp_path / "events.jsonl"
    first = generate_events_for_batch(
        settings,
        processing_date="2026-07-15",
        batch_id="atlas-20260715",
        pipeline_run_id="atlas-airflow-20260715-test",
        seed=12345,
        output_path=output,
    )
    second = generate_events_for_batch(
        settings,
        processing_date="2026-07-15",
        batch_id="atlas-20260715",
        pipeline_run_id="atlas-airflow-20260715-test2",
        seed=12345,
        output_path=output,
    )
    assert first.reused_existing is False
    assert second.reused_existing is True
    assert first.checksum_sha256 == second.checksum_sha256


def test_regeneration_to_fresh_path_is_byte_identical(tmp_path) -> None:
    """Same batch identity must regenerate identical bytes without artifact reuse.

    Guards against nondeterministic sources (uuid4/os.urandom) sneaking into
    generation: cross-machine reproducibility is what makes deployment smoke
    batches and integration tests comparable.
    """
    settings = load_settings()
    first = generate_events_for_batch(
        settings,
        processing_date="2026-07-15",
        batch_id="atlas-20260715",
        pipeline_run_id="atlas-airflow-20260715-a",
        seed=12345,
        output_path=tmp_path / "a.jsonl",
    )
    second = generate_events_for_batch(
        settings,
        processing_date="2026-07-15",
        batch_id="atlas-20260715",
        pipeline_run_id="atlas-airflow-20260715-b",
        seed=12345,
        output_path=tmp_path / "b.jsonl",
    )
    assert first.reused_existing is False
    assert second.reused_existing is False
    assert first.checksum_sha256 == second.checksum_sha256
    assert (tmp_path / "a.jsonl").read_bytes() == (tmp_path / "b.jsonl").read_bytes()
