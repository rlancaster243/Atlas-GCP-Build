"""Pipeline orchestration for Project Atlas Sprint 1.

Purpose:
    Coordinate generate → upload → load → validate as an end-to-end batch run.

Interactions:
    Invoked by ``scripts/run_pipeline.py`` and acceptance tests. Each step uses
    shared settings, logging, and run identifiers.

Engineering principles:
    - Independent scripts remain runnable on their own.
    - Orchestrator adds sequencing, logging, and failure propagation only.

Common failure modes:
    - Partial success leaves GCS object without BigQuery rows.
    - Validation FAIL is expected for seeded anomalies; callers must inspect
      acceptance checks separately.

Implementation choice:
    A thin Python orchestrator was chosen over Airflow for Sprint 1 because
    orchestration belongs to v0.4. Alternatives considered: Makefile-only flow
    (weaker error propagation) and Cloud Functions (out of scope).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import google.cloud.storage as storage
from google.cloud import bigquery

from atlas.config.settings import AtlasSettings, load_settings
from atlas.generator.events import GenerationResult, generate_events
from atlas.ingestion.upload import UploadResult, upload_events_file
from atlas.loader.bigquery import LoadResult, load_events_from_gcs
from atlas.logging.structured import StepLogger, configure_logging, new_pipeline_run_id
from atlas.validation.checks import ValidationReport, validate_anomaly_detection, validate_loaded_run


@dataclass(frozen=True)
class PipelineResult:
    """Aggregate result of a full pipeline run."""

    pipeline_run_id: str
    generation: GenerationResult
    upload: UploadResult | None
    load: LoadResult | None
    validation: ValidationReport | None
    log_file: Path


def run_pipeline(
    settings: AtlasSettings | None = None,
    *,
    pipeline_run_id: str | None = None,
    skip_upload: bool = False,
    skip_load: bool = False,
    skip_validation: bool = False,
    storage_client: storage.Client | None = None,
    bigquery_client: bigquery.Client | None = None,
) -> PipelineResult:
    """Execute the Sprint 1 Atlas pipeline."""
    settings = settings or load_settings()
    pipeline_run_id = pipeline_run_id or new_pipeline_run_id()
    logger = configure_logging(settings.logging.log_dir, pipeline_run_id)

    with StepLogger(logger, pipeline_run_id, "generate") as step:
        generation = generate_events(settings)
        step.rows_processed = generation.event_count
        step.details = {"output_path": str(generation.output_path)}

    upload_result: UploadResult | None = None
    load_result: LoadResult | None = None
    validation_report: ValidationReport | None = None

    if not skip_upload:
        with StepLogger(
            logger,
            pipeline_run_id,
            "upload",
            source_file=str(generation.output_path),
        ) as step:
            upload_result = upload_events_file(
                settings,
                generation.output_path,
                generation.primary_event_date,
                pipeline_run_id,
                client=storage_client,
            )
            step.rows_processed = generation.event_count
            step.details = {
                "gcs_uri": upload_result.gcs_uri,
                "already_exists": upload_result.already_exists,
            }

    if not skip_load and upload_result is not None:
        with StepLogger(
            logger,
            pipeline_run_id,
            "load",
            source_file=upload_result.gcs_uri,
        ) as step:
            load_result = load_events_from_gcs(
                settings,
                upload_result.gcs_uri,
                upload_result.gcs_uri,
                pipeline_run_id,
                client=bigquery_client,
            )
            step.rows_processed = load_result.rows_loaded
            step.details = {
                "target_table": load_result.target_table,
                "already_loaded": load_result.already_loaded,
            }

    if not skip_validation and load_result is not None:
        with StepLogger(
            logger,
            pipeline_run_id,
            "validate",
            source_file=load_result.source_file,
        ) as step:
            validation_report = validate_loaded_run(
                settings,
                pipeline_run_id,
                generation.primary_event_date,
                client=bigquery_client,
            )
            validation_report = validate_anomaly_detection(validation_report, settings)
            step.details = validation_report.to_dict()
            step.rows_processed = generation.event_count

    log_file = settings.logging.log_dir / f"{pipeline_run_id}.jsonl"
    return PipelineResult(
        pipeline_run_id=pipeline_run_id,
        generation=generation,
        upload=upload_result,
        load=load_result,
        validation=validation_report,
        log_file=log_file,
    )


def summarize_result(result: PipelineResult) -> dict[str, Any]:
    """Return a concise pipeline summary for CLI output."""
    return {
        "pipeline_run_id": result.pipeline_run_id,
        "generated_events": result.generation.event_count,
        "upload_uri": result.upload.gcs_uri if result.upload else None,
        "loaded_rows": result.load.rows_loaded if result.load else None,
        "validation_status": result.validation.overall_status if result.validation else None,
        "acceptance_status": (
            "PASS"
            if result.validation
            and all(
                check.status == "PASS"
                for check in result.validation.checks
                if check.name.startswith("acceptance_")
            )
            else "FAIL"
            if result.validation
            else None
        ),
        "log_file": str(result.log_file),
    }
