"""Composer path configuration tests."""

from __future__ import annotations

from pathlib import Path


def test_no_hardcoded_de_project_path_in_dags() -> None:
    dags_dir = Path(__file__).resolve().parents[2] / "dags"
    for path in dags_dir.rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        assert "Atlas-GCP-Build" not in content
        assert "~/project-atlas" not in content


def test_atlas_root_override_in_settings(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_ROOT", str(tmp_path))
    from atlas.config.settings import atlas_root

    assert atlas_root() == tmp_path.resolve()


def test_command_paths_use_atlas_root_env(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_ROOT", "/home/airflow/gcs/data/project-atlas")
    from atlas_orchestration.commands import scripts_dir

    assert str(scripts_dir()).startswith("/home/airflow/gcs/data/project-atlas")
