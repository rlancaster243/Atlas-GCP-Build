#!/usr/bin/env bash
# Ledger-driven Atlas schema migrations (Sprint 4, Phase 9).
#
# Usage:
#   apply_atlas_migrations.sh --mode plan     # show pending/applied, no mutation
#   apply_atlas_migrations.sh --mode status   # dump atlas_ops.schema_migrations
#   apply_atlas_migrations.sh --mode apply    # apply pending (requires ATLAS_APPROVE_DEPLOY=true)
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
PYTHONPATH="$(pwd)/src:${PYTHONPATH:-}"
export PYTHONPATH
PY="${ATLAS_PYTHON:-python3}"

MODE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

case "$MODE" in
  plan)
    "$PY" - <<'PY'
from atlas.ops.migrations import plan_migrations

plan = plan_migrations()
bad = [e for e in plan if e.state in ("CHECKSUM_MISMATCH", "FAILED_PREVIOUSLY")]
for entry in plan:
    print(f"  {entry.state:<18} {entry.migration_id}  ({entry.checksum[:12]}…)")
pending = sum(1 for e in plan if e.state == "PENDING")
print(f"plan: {pending} pending, {len(plan) - pending - len(bad)} applied, {len(bad)} blocking")
raise SystemExit(1 if bad else 0)
PY
    ;;
  status)
    "$PY" - <<'PY'
import json

from atlas.ops.migrations import migration_status

print(json.dumps(migration_status(), indent=2, default=str))
PY
    ;;
  apply)
    if [[ "${ATLAS_APPROVE_DEPLOY:-false}" != "true" ]]; then
      echo "ATLAS_APPROVE_DEPLOY != true — refusing to apply migrations." >&2
      exit 3
    fi
    "$PY" - <<'PY'
from atlas.ops.migrations import apply_migrations

for entry in apply_migrations():
    print(f"  {entry.state:<12} {entry.migration_id}  ({entry.checksum[:12]}…)")
print("migrations applied")
PY
    ;;
  *)
    echo "Usage: $0 --mode plan|apply|status" >&2
    exit 2
    ;;
esac
