"""Command builders for Atlas Airflow BashOperator tasks."""

from __future__ import annotations

import json
import os
import shlex
from pathlib import Path
from typing import Any


def atlas_root() -> Path:
    """Resolve Atlas runtime root without importing atlas.config at DAG parse time."""
    return Path(os.environ.get("ATLAS_ROOT", Path(__file__).resolve().parents[2])).expanduser()


def scripts_dir() -> Path:
    return atlas_root() / "scripts"


def dbt_project_dir() -> Path:
    return Path(os.environ.get("DBT_PROJECT_DIR", atlas_root() / "dbt" / "atlas_dbt"))


def run_atlas_step_command(step: str, context: dict[str, Any]) -> str:
    """Build a shell command invoking the Atlas step dispatcher."""
    payload = json.dumps(context)
    return (
        f"{shlex.quote(str(scripts_dir() / 'run_atlas_step.sh'))} {shlex.quote(step)} {shlex.quote(payload)}"
    )


def generate_events_command(context: dict[str, Any]) -> str:
    return run_atlas_step_command("generate_events", context)


def upload_events_command(context: dict[str, Any]) -> str:
    return run_atlas_step_command("upload_events", context)


def load_events_command(context: dict[str, Any]) -> str:
    return run_atlas_step_command("load_events", context)


def validate_raw_command(context: dict[str, Any]) -> str:
    return run_atlas_step_command("validate_raw_load", context)


def ensure_audit_command(context: dict[str, Any]) -> str:
    return run_atlas_step_command("ensure_audit_resources", context)


def start_audit_command(context: dict[str, Any]) -> str:
    return run_atlas_step_command("start_run_audit", context)


def preflight_command(context: dict[str, Any]) -> str:
    return run_atlas_step_command("preflight_environment", context)


def dbt_seed_command(context: dict[str, Any]) -> str:
    return run_atlas_step_command("dbt_seed", context)


def dbt_freshness_command(context: dict[str, Any]) -> str:
    return run_atlas_step_command("dbt_source_freshness", context)


def dbt_build_command(context: dict[str, Any]) -> str:
    return run_atlas_step_command("dbt_build", context)


def validate_warehouse_command(context: dict[str, Any]) -> str:
    return run_atlas_step_command("validate_warehouse", context)


def publish_marker_command(context: dict[str, Any]) -> str:
    return run_atlas_step_command("publish_success_marker", context)


def write_summary_command(context: dict[str, Any]) -> str:
    return run_atlas_step_command("write_run_summary", context)
