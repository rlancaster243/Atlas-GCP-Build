#!/usr/bin/env python3
"""Run the full Atlas Sprint 1 pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from atlas.config.settings import load_settings
from atlas.pipeline.orchestrator import run_pipeline, summarize_result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Atlas Sprint 1 end-to-end")
    parser.add_argument("--approve-provision", action="store_true", help="Required to mutate GCP resources")
    parser.add_argument("--run-id")
    args = parser.parse_args()

    if not args.approve_provision:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "message": (
                        "Live GCP provisioning is gated. Re-run with --approve-provision "
                        "after reviewing docs/runbook.md."
                    ),
                },
                indent=2,
            )
        )
        return 2

    settings = load_settings()
    result = run_pipeline(settings, pipeline_run_id=args.run_id)
    summary = summarize_result(result)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
