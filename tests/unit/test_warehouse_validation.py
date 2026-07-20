"""Unit tests for batch-scoped warehouse validation (Sprint 4 Phase 1)."""

from __future__ import annotations

from typing import Any

import pytest

from atlas.config.settings import load_settings
from atlas.validation.warehouse import validate_warehouse, warehouse_table


class FakeRow:
    def __init__(self, value: Any) -> None:
        self._value = value

    def values(self) -> list[Any]:
        return [self._value]


class FakeJob:
    def __init__(self, value: Any) -> None:
        self._value = value

    def result(self) -> list[FakeRow]:
        return [FakeRow(self._value)]


class FakeClient:
    """Returns scripted scalar answers keyed by an ordered list."""

    def __init__(self, answers: list[Any]) -> None:
        self._answers = list(answers)
        self.queries: list[str] = []

    def query(self, sql: str, job_config: Any = None) -> FakeJob:
        self.queries.append(sql)
        return FakeJob(self._answers.pop(0))


RAW = 50_000
ACCEPTED = 48_800
REJECTED = 1_200


def _happy_answers() -> list[Any]:
    # Order matches the check sequence in validate_warehouse.
    return [
        RAW,  # raw count (batch_nonempty + raw_equals_classification)
        RAW,  # classification count
        ACCEPTED,  # accepted count
        REJECTED,  # rejected count
        ACCEPTED,  # fact join count
        0,  # duplicate fact ids
        0,  # orphan users
        0,  # orphan countries
        123_456,  # mart total
        123_456,  # fact total
        0,  # bad processing dates
        0,  # null lineage
    ]


def test_validate_warehouse_passes_when_all_reconcile() -> None:
    client = FakeClient(_happy_answers())
    report = validate_warehouse("atlas-20260718", "2026-07-18", load_settings(), client=client)
    assert report.overall_status == "PASS"
    assert {c.name for c in report.checks} == {
        "batch_nonempty",
        "raw_equals_classification",
        "accepted_plus_rejected_equals_raw",
        "accepted_equals_fact",
        "fact_event_ids_unique",
        "fact_user_fk_resolves",
        "fact_country_fk_resolves",
        "mart_totals_reconcile",
        "processing_date_semantics",
        "batch_lineage_semantics",
    }


def test_validate_warehouse_fails_on_missing_batch() -> None:
    answers = _happy_answers()
    answers[0] = 0
    answers[1] = 0
    client = FakeClient(answers)
    report = validate_warehouse("atlas-19990101", "1999-01-01", load_settings(), client=client)
    assert report.overall_status == "FAIL"
    failed = {c.name for c in report.checks if c.status == "FAIL"}
    assert "batch_nonempty" in failed


@pytest.mark.parametrize(
    ("index", "bad_value", "expected_failed_check"),
    [
        (1, RAW - 10, "raw_equals_classification"),
        (3, REJECTED + 1, "accepted_plus_rejected_equals_raw"),
        (4, ACCEPTED - 5, "accepted_equals_fact"),
        (5, 3, "fact_event_ids_unique"),
        (6, 2, "fact_user_fk_resolves"),
        (7, 1, "fact_country_fk_resolves"),
        (9, 999, "mart_totals_reconcile"),
        (10, 42, "processing_date_semantics"),
        (11, 7, "batch_lineage_semantics"),
    ],
)
def test_validate_warehouse_fails_each_reconciliation(
    index: int, bad_value: Any, expected_failed_check: str
) -> None:
    answers = _happy_answers()
    answers[index] = bad_value
    client = FakeClient(answers)
    report = validate_warehouse("atlas-20260718", "2026-07-18", load_settings(), client=client)
    assert report.overall_status == "FAIL"
    failed = {c.name for c in report.checks if c.status == "FAIL"}
    assert expected_failed_check in failed


def test_validate_warehouse_never_trivially_passes_regression() -> None:
    """Regression: the Sprint 3 step printed a hardcoded PASS for any input."""
    answers = [0] * 8 + [0, 0, 0, 0]
    client = FakeClient(answers)
    report = validate_warehouse("atlas-empty", "2026-01-01", load_settings(), client=client)
    assert report.overall_status == "FAIL"


def test_warehouse_table_uses_dbt_dataset_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_DBT_DATASET", "atlas_ci_123")
    assert warehouse_table("proj", "core", "fct_events") == "proj.atlas_ci_123_core.fct_events"
    monkeypatch.delenv("ATLAS_DBT_DATASET")
    assert warehouse_table("proj", "marts", "m") == "proj.atlas_marts.m"
