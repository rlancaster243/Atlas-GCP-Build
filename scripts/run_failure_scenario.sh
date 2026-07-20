#!/usr/bin/env bash
# Atlas controlled failure-scenario runner (Sprint 6, ADR-013).
#
# Usage:
#   run_failure_scenario.sh <plan|run|verify|recover|cleanup|status|validate> \
#       --scenario S6-XXX-NNN --environment atlas-dev [--batch-id atlas-s6-...]
#
# Safety contract (enforced in atlas.failure_injection.framework and tested):
#   - disabled by default; an explicit scenario id is always required
#   - run/cleanup require ATLAS_APPROVE_FAILURE_INJECTION=true plus any
#     scenario-specific approvals (IAM, destructive fixture, rollback test)
#   - refuses scheduled execution, canonical batch ids, and production-style
#     environments
#   - every scenario carries a hard timeout and cost ceiling
#   - there is no silent fallback to normal execution: refusal exits nonzero
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ATLAS_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <plan|run|verify|recover|cleanup|status|validate> --scenario <id> --environment <env> [--batch-id <id>]" >&2
  exit 64
fi

COMMAND="$1"
shift

# Refuse to run inside a scheduled Airflow context outright — belt to the
# framework's suspenders. Drills are always operator-triggered.
if [[ "${AIRFLOW_CTX_DAG_RUN_TYPE:-}" == "scheduled" ]]; then
  echo "REFUSED: fault-injection commands never run inside scheduled Airflow execution" >&2
  exit 2
fi

# The scenario id must also be exported for the framework's explicit-parameter
# gate when running the gated commands.
if [[ "${COMMAND}" == "run" ]]; then
  scenario=""
  args=("$@")
  for i in "${!args[@]}"; do
    if [[ "${args[$i]}" == "--scenario" ]]; then
      scenario="${args[$((i + 1))]:-}"
    fi
  done
  if [[ -z "${scenario}" ]]; then
    echo "REFUSED: run requires an explicit --scenario" >&2
    exit 64
  fi
  export ATLAS_INJECTION_SCENARIO="${scenario}"
fi

PYTHONPATH="${ATLAS_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}" \
  exec python3 -m atlas.failure_injection.cli "${COMMAND}" "$@"
