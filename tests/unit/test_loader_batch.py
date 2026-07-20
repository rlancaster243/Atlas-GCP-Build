"""Unit tests for batch-scoped BigQuery load evaluation."""

from __future__ import annotations

import pytest

from atlas.loader.bigquery import BatchLoadState, evaluate_batch_load


def test_evaluate_batch_load_actions() -> None:
    assert evaluate_batch_load(BatchLoadState(0, 0), 50000) == "load"
    assert evaluate_batch_load(BatchLoadState(50000, 1), 50000) == "skip"


def test_evaluate_batch_load_partial_fails() -> None:
    with pytest.raises(ValueError, match="Partial batch"):
        evaluate_batch_load(BatchLoadState(100, 1), 50000)


def test_evaluate_batch_load_excess_fails() -> None:
    with pytest.raises(ValueError, match="Conflicting batch"):
        evaluate_batch_load(BatchLoadState(60000, 1), 50000)
