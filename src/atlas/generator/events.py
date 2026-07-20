"""Synthetic event generator for Project Atlas Sprint 1.

Purpose:
    Produce 50,000 reproducible JSON events with seeded data-quality anomalies.

Interactions:
    Writes local JSONL consumed by ingestion upload and referenced by validation
    acceptance tests via ``config/anomaly_profile.yaml``.

Engineering principles:
    - Deterministic random seed for reproducibility.
    - Explicit anomaly injection for validation and failure simulation.

Common failure modes:
    - Output directory missing or not writable.
    - Anomaly counts exceeding total event count.

Implementation choice:
    Pure Python generation keeps Cloud Shell execution simple and testable.
    Alternatives considered: Faker (extra dependency) and SQL generation
    (premature for raw JSONL ingestion).
"""

from __future__ import annotations

import json
import random
import uuid
from collections.abc import Iterator
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from atlas.batch.context import resolve_batch_context
from atlas.batch.manifest import (
    BatchManifest,
    compute_file_checksum,
    manifests_match,
    read_manifest,
    write_manifest,
)
from atlas.config.settings import AnomalyProfile, AtlasSettings


@dataclass(frozen=True)
class EventRecord:
    """Canonical Atlas raw event schema."""

    event_id: str
    user_id: str | None
    event_name: str
    event_timestamp: str
    event_date: str
    country_code: str
    platform: str
    app_version: str
    ingested_at: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        """Convert the event to JSONL fields (ingested_at is added at load time)."""
        payload = asdict(self)
        payload.pop("ingested_at", None)
        return payload


@dataclass(frozen=True)
class GenerationResult:
    """Summary of a generator run."""

    output_path: Path
    event_count: int
    anomaly_counts: dict[str, int]
    primary_event_date: str
    batch_id: str | None = None
    pipeline_run_id: str | None = None
    seed: int | None = None
    reused_existing: bool = False
    checksum_sha256: str | None = None


def _random_timestamp(rng: random.Random, base_day: date) -> datetime:
    """Create a timestamp within the base day."""
    hour = rng.randint(0, 23)
    minute = rng.randint(0, 59)
    second = rng.randint(0, 59)
    return datetime(base_day.year, base_day.month, base_day.day, hour, minute, second, tzinfo=UTC)


def _base_event(
    rng: random.Random,
    profile: AnomalyProfile,
    base_day: date,
    event_id: str | None = None,
) -> EventRecord:
    """Create a valid baseline event."""
    timestamp = _random_timestamp(rng, base_day)
    # Derive the UUID from the seeded RNG (not uuid4/os.urandom) so the same
    # batch identity regenerates byte-identical artifacts on any machine.
    return EventRecord(
        event_id=event_id or str(uuid.UUID(int=rng.getrandbits(128), version=4)),
        user_id=str(rng.randint(1, 100000)),
        event_name=rng.choice(profile.event_names),
        event_timestamp=timestamp.isoformat(),
        event_date=timestamp.date().isoformat(),
        country_code=rng.choice(profile.valid_country_codes),
        platform=rng.choice(profile.platforms),
        app_version=rng.choice(profile.app_versions),
    )


def _generate_event_rows(
    settings: AtlasSettings,
    *,
    seed: int,
    processing_date: str,
) -> tuple[list[EventRecord], dict[str, int], str]:
    profile = settings.anomaly_profile
    rng = random.Random(seed)
    base_day = date.fromisoformat(processing_date)
    events: list[EventRecord] = []
    anomaly_counts = {name: 0 for name in profile.anomalies}

    total = settings.generator.event_count
    for _ in range(total):
        events.append(_base_event(rng, profile, base_day))

    duplicate_count = profile.expected_count("duplicate_event_ids")
    group_size = 2
    num_groups = duplicate_count // group_size
    source_indices = rng.sample(range(total), num_groups)
    reserved = set(source_indices)
    target_candidates = [index for index in range(total) if index not in reserved]
    target_indices = rng.sample(target_candidates, num_groups)
    for source_index, target_index in zip(source_indices, target_indices, strict=True):
        events[target_index] = replace(events[target_index], event_id=events[source_index].event_id)
        anomaly_counts["duplicate_event_ids"] += 1

    for index in rng.sample(range(total), profile.expected_count("null_user_ids")):
        events[index] = replace(events[index], user_id=None)
        anomaly_counts["null_user_ids"] += 1

    invalid_countries = ["XX", "ZZ", "INVALID"]
    for index in rng.sample(range(total), profile.expected_count("invalid_country_codes")):
        events[index] = replace(events[index], country_code=rng.choice(invalid_countries))
        anomaly_counts["invalid_country_codes"] += 1

    for index in rng.sample(range(total), profile.expected_count("future_timestamps")):
        original = events[index]
        future_day = base_day + timedelta(days=rng.randint(1, 7))
        future_ts = datetime(
            future_day.year,
            future_day.month,
            future_day.day,
            12,
            0,
            0,
            tzinfo=UTC,
        )
        events[index] = replace(
            original,
            event_timestamp=future_ts.isoformat(),
            event_date=future_ts.date().isoformat(),
        )
        anomaly_counts["future_timestamps"] += 1

    for index in rng.sample(range(total), profile.expected_count("late_arriving_events")):
        original = events[index]
        late_date = base_day - timedelta(days=rng.randint(1, 5))
        timestamp = datetime.fromisoformat(original.event_timestamp)
        events[index] = replace(
            original,
            event_date=late_date.isoformat(),
            event_timestamp=timestamp.isoformat(),
        )
        anomaly_counts["late_arriving_events"] += 1

    return events, anomaly_counts, base_day.isoformat()


def write_jsonl(path: Path, records: Iterator[dict[str, str | None]]) -> None:
    """Write records to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, default=str))
            handle.write("\n")


def generate_events(settings: AtlasSettings) -> GenerationResult:
    """Generate seeded synthetic events and write JSONL output."""
    return generate_events_for_batch(
        settings,
        processing_date=date.today().isoformat(),
        batch_id=None,
        pipeline_run_id=None,
        seed=settings.generator.random_seed,
        output_path=settings.generator.output_dir / f"events_seed_{settings.generator.random_seed}.jsonl",
    )


def generate_events_for_batch(
    settings: AtlasSettings,
    *,
    processing_date: str,
    batch_id: str | None,
    pipeline_run_id: str | None,
    seed: int | None,
    output_path: Path | None = None,
) -> GenerationResult:
    """Generate or reuse a batch artifact for orchestrated runs."""
    resolved_batch_id: str | None
    resolved_pipeline_run_id: str | None
    if batch_id and pipeline_run_id:
        context = resolve_batch_context(
            processing_date=processing_date,
            batch_id=batch_id,
            pipeline_run_id=pipeline_run_id,
            seed=seed,
        )
        target_path = output_path or context.local_file_path
        manifest_path = context.manifest_path
        resolved_seed = context.seed
        resolved_batch_id = context.batch_id
        resolved_pipeline_run_id = context.pipeline_run_id

        if target_path.exists() and manifest_path.exists():
            existing_manifest = read_manifest(manifest_path)
            if existing_manifest is not None:
                requested_manifest = BatchManifest(
                    batch_id=resolved_batch_id,
                    processing_date=processing_date,
                    pipeline_run_id=resolved_pipeline_run_id,
                    seed=resolved_seed,
                    row_count=existing_manifest.row_count,
                    checksum_sha256=compute_file_checksum(target_path),
                    output_path=str(target_path),
                )
                if manifests_match(existing_manifest, requested_manifest):
                    return GenerationResult(
                        output_path=target_path,
                        event_count=existing_manifest.row_count,
                        anomaly_counts={},
                        primary_event_date=processing_date,
                        batch_id=existing_manifest.batch_id,
                        pipeline_run_id=existing_manifest.pipeline_run_id,
                        seed=existing_manifest.seed,
                        reused_existing=True,
                        checksum_sha256=existing_manifest.checksum_sha256,
                    )
                raise ValueError(
                    f"Existing batch artifact conflicts with requested batch identity for {target_path}"
                )
    else:
        target_path = output_path or (
            settings.generator.output_dir / f"events_seed_{settings.generator.random_seed}.jsonl"
        )
        manifest_path = target_path.with_suffix(".manifest.json")
        resolved_seed = seed if seed is not None else settings.generator.random_seed
        resolved_batch_id = batch_id
        resolved_pipeline_run_id = pipeline_run_id

    events, anomaly_counts, primary_event_date = _generate_event_rows(
        settings,
        seed=resolved_seed,
        processing_date=processing_date,
    )
    write_jsonl(target_path, (event.to_dict() for event in events))
    checksum = compute_file_checksum(target_path)
    manifest = BatchManifest(
        batch_id=resolved_batch_id or f"legacy-{resolved_seed}",
        processing_date=processing_date,
        pipeline_run_id=resolved_pipeline_run_id or f"legacy-{resolved_seed}",
        seed=resolved_seed,
        row_count=len(events),
        checksum_sha256=checksum,
        output_path=str(target_path),
    )
    write_manifest(manifest_path, manifest)

    return GenerationResult(
        output_path=target_path,
        event_count=len(events),
        anomaly_counts=anomaly_counts,
        primary_event_date=primary_event_date,
        batch_id=resolved_batch_id,
        pipeline_run_id=resolved_pipeline_run_id,
        seed=resolved_seed,
        reused_existing=False,
        checksum_sha256=checksum,
    )
