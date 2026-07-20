"""Environment preflight checks for orchestrated Atlas runs."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from atlas.config.settings import AtlasSettings, atlas_root, load_settings
from atlas.loader.bigquery import ensure_events_table
from atlas.observability.cost import labeled_bigquery_client
from atlas.ops.resources import ensure_audit_resources


@dataclass(frozen=True)
class PreflightResult:
    """Summary of environment validation."""

    status: str
    checks: list[str]
    atlas_root: str
    dbt_project_dir: str


def _check_path_exists(path: Path, label: str, checks: list[str]) -> None:
    if path.exists():
        checks.append(f"PASS {label}: {path}")
    else:
        checks.append(f"FAIL {label}: missing {path}")


def preflight_environment(
    settings: AtlasSettings | None = None,
    *,
    dbt_project_dir: Path | None = None,
    skip_gcp: bool = False,
) -> PreflightResult:
    """Validate Atlas runtime paths, scripts, and optional GCP resources."""
    settings = settings or load_settings()
    root = atlas_root()
    dbt_dir = dbt_project_dir or (root / "dbt" / "atlas_dbt")
    checks: list[str] = []

    _check_path_exists(root / "config" / "atlas.yaml", "atlas config", checks)
    _check_path_exists(root / "scripts" / "generate_events.py", "generate script", checks)
    _check_path_exists(root / "scripts" / "upload_events.py", "upload script", checks)
    _check_path_exists(root / "scripts" / "load_events.py", "load script", checks)
    _check_path_exists(root / "scripts" / "validate_events.py", "validate script", checks)
    _check_path_exists(root / "scripts" / "run_atlas_step.sh", "step dispatcher", checks)
    _check_path_exists(dbt_dir / "dbt_project.yml", "dbt project", checks)

    if shutil.which("dbt") is None:
        checks.append("WARN dbt CLI not on PATH (expected in Cloud Shell / venv)")
    else:
        checks.append("PASS dbt CLI available")

    if settings.gcp.project_id:
        checks.append(f"PASS GCP project configured: {settings.gcp.project_id}")
    else:
        checks.append("FAIL GCP project not configured")

    if settings.gcp.bucket_name:
        checks.append(f"PASS GCS bucket configured: {settings.gcp.bucket_name}")
    else:
        checks.append("FAIL GCS bucket not configured")

    if not skip_gcp:
        try:
            ensure_audit_resources(settings=settings)
            checks.append("PASS atlas_ops audit resources verified")
            ensure_events_table(
                labeled_bigquery_client(settings.gcp.project_id, "pipeline"),
                settings,
            )
            checks.append(f"PASS raw table verified: {settings.gcp.dataset_id}.{settings.gcp.table_id}")
        except Exception as exc:  # noqa: BLE001 - preflight captures operational failures
            checks.append(f"FAIL GCP preflight: {exc}")

    status = "PASS" if all(item.startswith("PASS") or item.startswith("WARN") for item in checks) else "FAIL"
    return PreflightResult(
        status=status,
        checks=checks,
        atlas_root=str(root),
        dbt_project_dir=str(dbt_dir),
    )
