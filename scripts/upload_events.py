#!/usr/bin/env python3
"""Upload generated Atlas events to Cloud Storage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from atlas.config.settings import load_settings
from atlas.ingestion.upload import upload_events_file
from atlas.logging.structured import new_pipeline_run_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload Atlas JSONL to GCS")
    parser.add_argument("--local-path", required=True, type=Path)
    parser.add_argument("--event-date", required=True)
    parser.add_argument("--run-id", default=new_pipeline_run_id())
    parser.add_argument("--batch-id")
    parser.add_argument("--expected-checksum")
    parser.add_argument(
        "--fail-once",
        action="store_true",
        help="Inject a transient failure for retry testing (development only)",
    )
    args = parser.parse_args()

    settings = load_settings()
    result = upload_events_file(
        settings,
        args.local_path,
        args.event_date,
        args.run_id,
        batch_id=args.batch_id,
        expected_checksum=args.expected_checksum,
        fail_once=args.fail_once,
    )
    print(json.dumps(result.__dict__, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
