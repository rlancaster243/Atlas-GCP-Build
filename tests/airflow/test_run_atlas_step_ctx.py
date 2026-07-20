"""Regression tests for run_atlas_step.sh JSON run-context passing.

Guards against the ``${2:-{}}`` bash default-value bug: bash parsed the default
as ``{`` plus a literal trailing ``}``, appending a stray ``}`` to a JSON object
argument and breaking ``json.loads`` in every orchestrated task ("Extra data").

The dispatcher parses the context before dispatching on the step name, so an
unrecognised step with a valid JSON context reaches the "Unknown step" branch
without importing GCP libraries or touching the network.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ATLAS_ROOT = Path(__file__).resolve().parents[2]
STEP_SCRIPT = ATLAS_ROOT / "scripts" / "run_atlas_step.sh"
_NOOP_STEP = "__regression_noop__"


def _run(*args: str) -> str:
    result = subprocess.run(
        ["bash", str(STEP_SCRIPT), _NOOP_STEP, *args],
        capture_output=True,
        text=True,
    )
    return result.stdout + result.stderr


def test_json_context_is_passed_through_intact() -> None:
    ctx = json.dumps({"batch_id": "atlas-20260718", "seed": 1, "upload_once": True})
    combined = _run(ctx)
    # Reaching the "Unknown step" branch proves json.loads succeeded.
    assert f"Unknown step: {_NOOP_STEP}" in combined, combined
    assert "invalid JSON context" not in combined
    assert "Extra data" not in combined


def test_missing_context_defaults_to_valid_json() -> None:
    combined = _run()
    assert f"Unknown step: {_NOOP_STEP}" in combined, combined
    assert "invalid JSON context" not in combined
