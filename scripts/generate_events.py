#!/usr/bin/env python3
"""Generate synthetic Atlas events."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from atlas.config.settings import load_settings
from atlas.generator.events import generate_events, generate_events_for_batch
from atlas.logging.structured import new_pipeline_run_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Atlas synthetic events")
    parser.add_argument("--processing-date", default=date.today().isoformat())
    parser.add_argument("--batch-id")
    parser.add_argument("--pipeline-run-id", default=new_pipeline_run_id())
    parser.add_argument("--seed", type=int)
    parser.add_argument("--output-path", type=Path)
    args = parser.parse_args()

    settings = load_settings()
    if args.batch_id:
        result = generate_events_for_batch(
            settings,
            processing_date=args.processing_date,
            batch_id=args.batch_id,
            pipeline_run_id=args.pipeline_run_id,
            seed=args.seed,
            output_path=args.output_path,
        )
    else:
        result = generate_events(settings)

    print(
        json.dumps(
            {
                "output_path": str(result.output_path),
                "event_count": result.event_count,
                "anomaly_counts": result.anomaly_counts,
                "primary_event_date": result.primary_event_date,
                "batch_id": result.batch_id,
                "pipeline_run_id": result.pipeline_run_id,
                "seed": result.seed,
                "reused_existing": result.reused_existing,
                "checksum_sha256": result.checksum_sha256,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
