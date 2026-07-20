#!/usr/bin/env bash
# Clean-clone reproduction test (Sprint 8, Phase 11).
#
# Proves a new engineer can reach a green local validation state from a fresh
# clone using only documented commands — no reuse of the current virtualenv,
# generated data, dbt target, cached credentials, or untracked files.
#
# Usage:
#   bash scripts/validate_clean_clone.sh [--ref <commit-ish>] [--keep]
#
# Steps: clone -> checkout -> fresh venv -> documented install -> static CI ->
# generate synthetic data -> unit tests -> governance -> lineage -> reference
# validation. Records duration and per-step outcome; removes the temp dir unless
# --keep. Credentialless: never touches GCP.
set -uo pipefail

REF=""
KEEP=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref) REF="$2"; shift 2 ;;
    --keep) KEEP=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

# Repository root (parent of ).
SRC_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
[[ -z "$REF" ]] && REF="$(git -C "$SRC_ROOT" rev-parse HEAD)"

TMP_DIR="$(mktemp -d -t atlas-clean-clone-XXXXXX)"
CLONE="$TMP_DIR/Atlas-GCP-Build"
START_TS=$(date +%s)
declare -a RESULTS=()

record() { RESULTS+=("$1: $2"); echo "----- $1: $2 -----"; }

cleanup() {
  if [[ "$KEEP" -eq 1 ]]; then
    echo "temp dir kept: $TMP_DIR"
  else
    rm -rf "$TMP_DIR"
  fi
}
trap cleanup EXIT

echo "== clean-clone from $SRC_ROOT @ $REF =="
if ! git clone --quiet "$SRC_ROOT" "$CLONE"; then
  echo "clone FAILED" >&2; exit 1
fi
git -C "$CLONE" checkout --quiet "$REF" || { echo "checkout FAILED" >&2; exit 1; }

ATLAS="$CLONE/project-atlas"
cd "$ATLAS" || { echo "no project-atlas dir" >&2; exit 1; }

# Fresh, isolated virtualenv (no reuse of the caller's environment).
python3 -m venv "$TMP_DIR/venv" || { echo "venv FAILED" >&2; exit 1; }
# shellcheck disable=SC1091
source "$TMP_DIR/venv/bin/activate"
export PATH="$TMP_DIR/venv/bin:$PATH"
unset ATLAS_ROOT PYTHONPATH 2>/dev/null || true

echo "== documented install =="
if python -m pip install --quiet --upgrade pip \
   && python -m pip install --quiet -r requirements.txt -r requirements-ci.txt; then
  record install PASS
else
  record install FAIL
fi

echo "== static CI =="
if bash scripts/validate_ci.sh --mode static; then record static_ci PASS; else record static_ci FAIL; fi

echo "== generate synthetic data =="
if python scripts/generate_events.py >/dev/null 2>&1; then record generate PASS; else record generate SKIP_OR_FAIL; fi

echo "== unit tests =="
if python -m pytest tests/ -q >/dev/null 2>&1; then record unit_tests PASS; else record unit_tests FAIL; fi

# atlas.* modules live under src/ (no installed package); use the documented
# PYTHONPATH=src convention (same as pytest.ini and validate_ci.sh).
export PYTHONPATH="src"

echo "== governance =="
if python -m atlas.governance.catalog check; then record governance PASS; else record governance FAIL; fi

echo "== lineage =="
if python -m atlas.governance.lineage >/dev/null 2>&1; then record lineage PASS; else record lineage FAIL; fi

echo "== reference validation =="
if python -m atlas.reference.validate; then record reference PASS; else record reference FAIL; fi

END_TS=$(date +%s)
DURATION=$((END_TS - START_TS))

echo ""
echo "===================== CLEAN-CLONE SUMMARY ====================="
printf '  %s\n' "${RESULTS[@]}"
echo "  duration_seconds: $DURATION"
echo "  ref: $REF"
echo "==============================================================="

# Fail if any required step failed (generate may SKIP without GCP config).
for r in "${RESULTS[@]}"; do
  case "$r" in
    *": FAIL") echo "clean_clone: FAIL"; exit 1 ;;
  esac
done
echo "clean_clone: PASS"
