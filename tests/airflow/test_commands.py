"""Command builder tests."""

from __future__ import annotations

from atlas_orchestration.commands import atlas_root, run_atlas_step_command


def test_run_atlas_step_command_includes_step_and_context() -> None:
    cmd = run_atlas_step_command("generate_events", {"batch_id": "atlas-20260715"})
    assert "run_atlas_step.sh" in cmd
    assert "generate_events" in cmd


def test_atlas_root_honors_env(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_ROOT", "/composer/data/project-atlas")
    assert str(atlas_root()) == "/composer/data/project-atlas"
