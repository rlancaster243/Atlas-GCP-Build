#!/usr/bin/env python3
"""Validate a loaded Atlas pipeline run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from atlas.config.settings import load_settings
from atlas.validation.checks import validate_anomaly_detection, validate_loaded_run


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Atlas loaded events")
    parser.add_argument("--run-id")
    parser.add_argument("--event-date", required=True)
    parser.add_argument("--batch-id")
    parser.add_argument("--processing-date")
    parser.add_argument(
        "--mode",
        choices=("sprint1", "airflow"),
        default="sprint1",
        help="airflow mode scopes by batch_id and uses structural PASS criteria",
    )
    args = parser.parse_args()

    if not args.run_id and not args.batch_id:
        parser.error("Provide --run-id or --batch-id")

    settings = load_settings()
    report = validate_loaded_run(
        settings,
        args.run_id or args.batch_id or "",
        args.event_date,
        batch_id=args.batch_id,
        processing_date=args.processing_date or args.event_date,
        mode=args.mode,
    )
    if args.mode == "sprint1":
        report = validate_anomaly_detection(report, settings)
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.overall_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
