#!/usr/bin/env bash
# Atlas BigQuery performance suite (Sprint 7, Phase 10-11).
#
# Dry-runs every representative query (bills $0) to capture bytes-processed
# baselines. When ATLAS_APPROVE_PERFORMANCE_TESTS=true it also EXECUTES each
# query under a per-query maximum_bytes_billed ceiling and a cumulative suite
# ceiling, capturing bytes billed, slot-ms, and elapsed. Results are written to
# observability/performance/results/.
#
# Usage:
#   bash scripts/run_performance_suite.sh [--project P] [--location US] [--execute]
set -euo pipefail

ATLAS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="${ATLAS_GCP_PROJECT_ID:-example-gcp-project}"
LOCATION="${ATLAS_BQ_LOCATION:-US}"
EXECUTE="false"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    --location) LOCATION="$2"; shift 2 ;;
    --execute) EXECUTE="true"; shift ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

if [[ "$EXECUTE" == "true" && "${ATLAS_APPROVE_PERFORMANCE_TESTS:-}" != "true" ]]; then
  echo "ERROR: --execute requires ATLAS_APPROVE_PERFORMANCE_TESTS=true" >&2
  exit 3
fi

QUERY_DIR="${ATLAS_ROOT}/observability/performance/queries"
OUT_DIR="${ATLAS_ROOT}/observability/performance/results"
mkdir -p "$OUT_DIR"

PROJECT="$PROJECT" LOCATION="$LOCATION" EXECUTE="$EXECUTE" QUERY_DIR="$QUERY_DIR" \
OUT_DIR="$OUT_DIR" PYTHONPATH="${ATLAS_ROOT}/src" python3 - <<'PY'
import json
import os
import time
from pathlib import Path

from google.cloud import bigquery

from atlas.observability.cost_guard import max_performance_suite_bytes, max_query_bytes

project = os.environ["PROJECT"]
location = os.environ["LOCATION"]
execute = os.environ["EXECUTE"] == "true"
query_dir = Path(os.environ["QUERY_DIR"])
out_dir = Path(os.environ["OUT_DIR"])

client = bigquery.Client(project=project, location=location)
suite_ceiling = max_performance_suite_bytes("atlas-dev")
per_query_ceiling = max_query_bytes("atlas-dev")

results = []
cumulative_billed = 0
# Exclude the deliberately-unbounded fixture from the normal suite.
queries = sorted(q for q in query_dir.glob("*.sql") if q.stem != "unbounded_scan")

for q in queries:
    sql = q.read_text().replace("${PROJECT}", project)
    dry = client.query(
        sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    )
    estimated = int(dry.total_bytes_processed or 0)
    record = {
        "query": q.stem,
        "estimated_bytes": estimated,
        "within_per_query_ceiling": estimated <= per_query_ceiling,
    }
    if execute:
        if cumulative_billed + estimated > suite_ceiling:
            record["executed"] = False
            record["skipped_reason"] = "would exceed suite byte ceiling"
            results.append(record)
            continue
        cfg = bigquery.QueryJobConfig(
            maximum_bytes_billed=per_query_ceiling,
            labels={"atlas_component": "perf_suite", "atlas_sprint": "7"},
            use_query_cache=False,
        )
        start = time.time()
        job = client.query(sql, job_config=cfg)
        rows = list(job.result())
        elapsed_ms = int((time.time() - start) * 1000)
        billed = int(job.total_bytes_billed or 0)
        cumulative_billed += billed
        record.update(
            {
                "executed": True,
                "bytes_billed": billed,
                "slot_ms": int(job.slot_millis or 0),
                "elapsed_ms": elapsed_ms,
                "output_rows": len(rows),
                "cache_hit": bool(job.cache_hit),
                "correctness_checksum": str(rows[0]) if rows else "empty",
            }
        )
    results.append(record)

payload = {
    "project": project,
    "location": location,
    "executed": execute,
    "per_query_ceiling_bytes": per_query_ceiling,
    "suite_ceiling_bytes": suite_ceiling,
    "cumulative_bytes_billed": cumulative_billed,
    "queries": results,
}
mode = "executed" if execute else "dryrun"
out = out_dir / f"baseline-{mode}.json"
out.write_text(json.dumps(payload, indent=2) + "\n")
print(json.dumps(payload, indent=2))
print(f"\nwrote {out}")
PY
