"""Regression tests for Sprint 4 Phase 1 hygiene fixes.

Guards against reintroducing:
- `|| true` suppression on required Airflow gates in test_airflow_sprint3.sh,
- trigger-without-poll behavior in run_airflow_sprint3.sh,
- the hardcoded validate_warehouse PASS in atlas_step_runner.py,
- obsolete feature-branch checkouts in the README quick starts.
"""

from __future__ import annotations

import re
from pathlib import Path

ATLAS_ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ATLAS_ROOT / relative).read_text(encoding="utf-8")


def test_airflow_gate_does_not_suppress_import_errors() -> None:
    content = _read("scripts/test_airflow_sprint3.sh")
    for line in content.splitlines():
        if "list-import-errors" in line and "import_errors=" not in line:
            assert "|| true" not in line, f"import-error gate is suppressed: {line.strip()}"
    assert "exit 1" in content, "gate must be able to fail"
    assert "atlas_batch_pipeline" in content


def test_airflow_gate_fails_when_dag_missing() -> None:
    content = _read("scripts/test_airflow_sprint3.sh")
    # The registration check must be a hard gate, not a soft grep.
    assert re.search(r"if\s+!\s+airflow dags list.*grep.*atlas_batch_pipeline", content, re.S)


def test_run_airflow_polls_to_terminal_state() -> None:
    content = _read("scripts/run_airflow_sprint3.sh")
    assert "dags state" in content, "must poll the triggered run"
    assert "RUN_TIMEOUT_SECONDS" in content, "must bound the poll"
    assert "dag_run_id" in content, "must capture the triggered run id"
    assert "states-for-dag-run" in content, "must report failed tasks"
    assert "query_pipeline_run" in content, "must report the audit row"
    assert "run-summary.json" in content, "must report the local summary path"
    # Success path exits 0, failure and timeout paths exit 1.
    assert re.search(r"success\)\s*\n.*", content)
    assert content.count("exit 1") >= 3


def test_step_runner_validate_warehouse_is_real() -> None:
    content = _read("scripts/atlas_step_runner.py")
    assert "dbt build tests cover warehouse validation" not in content, (
        "validate_warehouse must not return a hardcoded PASS"
    )
    assert "from atlas.validation.warehouse import validate_warehouse" in content
    assert 'report.overall_status == "PASS"' in content


def test_readme_quick_starts_use_main() -> None:
    content = _read("README.md")
    assert "git checkout cursor/atlas-sprint-2-dbt-warehouse-3660" not in content
    assert "git checkout cursor/atlas-sprint-3-airflow-orchestration-3660" not in content
    assert "git checkout main" in content


def test_readme_release_table_includes_sprint3() -> None:
    content = _read("README.md")
    assert "atlas-sprint-3-complete" in content
