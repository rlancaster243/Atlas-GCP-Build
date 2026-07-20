"""Finalizer reconciliation tests."""

from __future__ import annotations

from atlas.ops.finalizer import finalizer_should_fail, reconcile_run_summary


def test_reconcile_run_summary_detects_mismatch() -> None:
    local = {"pipeline_run_id": "a", "batch_id": "b", "status": "SUCCESS"}
    audit = {"pipeline_run_id": "a", "batch_id": "b", "status": "FAILED"}
    result = reconcile_run_summary(local, audit)
    assert result["reconciled"] is False


def test_finalizer_should_fail_on_failed_status() -> None:
    assert finalizer_should_fail({"status": "FAILED"}) is True
    assert finalizer_should_fail({"status": "SUCCESS"}) is False
