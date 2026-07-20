#!/usr/bin/env python3
"""Simulate common Atlas pipeline failure modes locally or against GCP."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from atlas.config.settings import load_settings
from atlas.generator.events import write_jsonl
from atlas.loader.bigquery import load_events_from_gcs
from atlas.validation.checks import validate_loaded_run


def simulate_missing_file() -> dict[str, str]:
    return {"scenario": "missing_file", "status": "FAILED", "message": "Source file not found"}


def simulate_bad_schema(tmp_path: Path) -> Path:
    bad_path = tmp_path / "bad_schema.jsonl"
    write_jsonl(bad_path, iter([{"event_id": "1", "unexpected": "field"}]))
    return bad_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulate Atlas failure scenarios")
    parser.add_argument(
        "--scenario",
        choices=["missing_file", "bad_schema", "duplicate_upload"],
        required=True,
    )
    args = parser.parse_args()

    settings = load_settings()
    if args.scenario == "missing_file":
        print(json.dumps(simulate_missing_file(), indent=2))
        return 1

    if args.scenario == "bad_schema":
        bad_path = simulate_bad_schema(Path(settings.generator.output_dir))
        print(json.dumps({"scenario": "bad_schema", "path": str(bad_path)}, indent=2))
        return 0

    if args.scenario == "duplicate_upload":
        print(
            json.dumps(
                {
                    "scenario": "duplicate_upload",
                    "status": "SKIPPED",
                    "message": "Requires live GCS credentials and --approve-provision",
                },
                indent=2,
            )
        )
        return 0

    _ = load_events_from_gcs
    _ = validate_loaded_run
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
