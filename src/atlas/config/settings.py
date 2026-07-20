"""Configuration loading and validation for Project Atlas.

Purpose:
    Centralizes runtime settings so every pipeline step reads the same
    project, bucket, dataset, and validation thresholds.

Interactions:
    Used by generator, ingestion, loader, validation, and CLI scripts.
    Reads ``config/atlas.yaml`` and ``config/anomaly_profile.yaml``.

Engineering principles:
    - Configuration over hardcoding for reproducibility across Cloud Shell
      and Cursor Cloud Agent environments.
    - Environment variable overrides keep secrets out of source control.

Common failure modes:
    - Missing ``GCP_PROJECT_ID`` or ``ATLAS_GCP_PROJECT_ID`` in cloud runs.
    - Bucket name collisions if the logical name is used without project suffix.

Implementation choice:
    YAML + dataclasses were chosen over environment-only config because Sprint 1
    needs documented defaults and anomaly profiles that acceptance tests can
    assert against. Alternatives considered: pure env vars (harder to review)
    and Pydantic Settings (heavier dependency for a focused pipeline).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "atlas.yaml"
DEFAULT_ANOMALY_PATH = PROJECT_ROOT / "config" / "anomaly_profile.yaml"


def atlas_root() -> Path:
    """Return the Atlas project root, honoring ATLAS_ROOT for Composer layouts."""
    override = _env("ATLAS_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return PROJECT_ROOT


@dataclass(frozen=True)
class GcpConfig:
    """GCP resource identifiers for Atlas Sprint 1."""

    project_id: str
    location: str
    bucket_name: str
    bucket_logical_name: str
    dataset_id: str
    table_id: str


@dataclass(frozen=True)
class GeneratorConfig:
    """Synthetic event generator settings."""

    event_count: int
    random_seed: int
    output_dir: Path


@dataclass(frozen=True)
class IngestionConfig:
    """Cloud Storage ingestion settings."""

    gcs_prefix: str


@dataclass(frozen=True)
class LoaderConfig:
    """BigQuery loader settings."""

    staging_table_suffix: str


@dataclass(frozen=True)
class ValidationConfig:
    """Validation thresholds."""

    expected_event_count: int
    future_date_field: str


@dataclass(frozen=True)
class LoggingConfig:
    """Structured logging settings."""

    log_dir: Path
    log_format: str


@dataclass(frozen=True)
class AnomalyProfile:
    """Expected seeded anomaly counts for generator and acceptance tests."""

    anomalies: dict[str, dict[str, Any]]
    valid_country_codes: list[str]
    event_names: list[str]
    platforms: list[str]
    app_versions: list[str]

    def expected_count(self, anomaly_type: str) -> int:
        """Return configured anomaly count for a named anomaly type."""
        return int(self.anomalies[anomaly_type]["count"])


@dataclass(frozen=True)
class AtlasSettings:
    """Fully resolved Atlas runtime settings."""

    gcp: GcpConfig
    generator: GeneratorConfig
    ingestion: IngestionConfig
    loader: LoaderConfig
    validation: ValidationConfig
    logging: LoggingConfig
    anomaly_profile: AnomalyProfile
    config_path: Path
    anomaly_path: Path


def _env(name: str, default: str | None = None) -> str | None:
    """Read an environment variable with optional default."""
    return os.environ.get(name, default)


def _env_str(name: str, default: str) -> str:
    """Read an environment variable with a required string default."""
    value = os.environ.get(name)
    return value if value else default


def _require_env(*names: str) -> str:
    """Return the first populated environment variable."""
    for name in names:
        value = _env(name)
        if value:
            return value
    joined = ", ".join(names)
    raise ValueError(f"Required environment variable not set. Provide one of: {joined}")


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML document from disk."""
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_settings(
    config_path: Path | None = None,
    anomaly_path: Path | None = None,
) -> AtlasSettings:
    """Load and validate Atlas settings from YAML with env overrides."""
    root = atlas_root()
    config_path = config_path or root / "config" / "atlas.yaml"
    anomaly_path = anomaly_path or root / "config" / "anomaly_profile.yaml"

    raw = load_yaml(config_path)
    anomaly_raw = load_yaml(anomaly_path)

    project_id = _env_str("ATLAS_GCP_PROJECT_ID", _env_str("GCP_PROJECT_ID", raw["gcp"]["project_id"]))
    bucket_name = _env_str("ATLAS_GCS_BUCKET", raw["gcp"]["bucket_name"])

    gcp = GcpConfig(
        project_id=project_id,
        location=raw["gcp"]["location"],
        bucket_name=bucket_name,
        bucket_logical_name=raw["gcp"]["bucket_logical_name"],
        # ATLAS_BQ_DATASET matches the override dbt sources already honor,
        # and lets CI redirect raw loads into isolated atlas_ci_* datasets.
        dataset_id=_env_str("ATLAS_BQ_DATASET", raw["gcp"]["dataset_id"]),
        table_id=raw["gcp"]["table_id"],
    )
    generator = GeneratorConfig(
        event_count=int(_env_str("ATLAS_EVENT_COUNT", str(raw["generator"]["event_count"]))),
        random_seed=int(_env_str("ATLAS_RANDOM_SEED", str(raw["generator"]["random_seed"]))),
        output_dir=root / raw["generator"]["output_dir"],
    )
    ingestion = IngestionConfig(gcs_prefix=_env_str("ATLAS_GCS_PREFIX", raw["ingestion"]["gcs_prefix"]))
    loader = LoaderConfig(staging_table_suffix=raw["loader"]["staging_table_suffix"])
    validation = ValidationConfig(
        expected_event_count=int(
            _env_str("ATLAS_EXPECTED_EVENT_COUNT", str(raw["validation"]["expected_event_count"]))
        ),
        future_date_field=raw["validation"]["future_date_field"],
    )
    logging_cfg = LoggingConfig(
        log_dir=root / raw["logging"]["log_dir"],
        log_format=raw["logging"]["log_format"],
    )
    anomaly_profile = AnomalyProfile(
        anomalies=anomaly_raw["anomalies"],
        valid_country_codes=anomaly_raw["valid_country_codes"],
        event_names=anomaly_raw["event_names"],
        platforms=anomaly_raw["platforms"],
        app_versions=anomaly_raw["app_versions"],
    )

    return AtlasSettings(
        gcp=gcp,
        generator=generator,
        ingestion=ingestion,
        loader=loader,
        validation=validation,
        logging=logging_cfg,
        anomaly_profile=anomaly_profile,
        config_path=config_path,
        anomaly_path=anomaly_path,
    )


def table_fqn(settings: AtlasSettings) -> str:
    """Return fully qualified BigQuery table name."""
    return f"{settings.gcp.project_id}.{settings.gcp.dataset_id}.{settings.gcp.table_id}"


def staging_table_id(settings: AtlasSettings, run_id: str) -> str:
    """Return a run-scoped staging table id."""
    safe_run_id = run_id.replace("-", "_")
    return f"{settings.gcp.table_id}{settings.loader.staging_table_suffix}_{safe_run_id}"
