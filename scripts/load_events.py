#!/usr/bin/env python3
"""Load Atlas events from Cloud Storage into BigQuery."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from atlas.config.settings import load_settings
from atlas.loader.bigquery import load_events_from_gcs
from atlas.logging.structured import new_pipeline_run_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Load Atlas JSONL from GCS to BigQuery")
    parser.add_argument("--gcs-uri", required=True)
    parser.add_argument("--run-id", default=new_pipeline_run_id())
    parser.add_argument("--batch-id")
    parser.add_argument("--processing-date")
    parser.add_argument("--expected-row-count", type=int)
    args = parser.parse_args()

    settings = load_settings()
    result = load_events_from_gcs(
        settings,
        args.gcs_uri,
        args.gcs_uri,
        args.run_id,
        batch_id=args.batch_id,
        processing_date=args.processing_date,
        expected_row_count=args.expected_row_count,
    )
    print(json.dumps(result.__dict__, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
