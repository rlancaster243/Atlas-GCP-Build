"""Parse-time side-effect guards."""

from __future__ import annotations

from pathlib import Path


def test_context_module_has_no_subprocess_or_network_imports() -> None:
    path = Path(__file__).resolve().parents[2] / "dags" / "atlas_orchestration" / "context.py"
    source = path.read_text(encoding="utf-8")
    assert "subprocess" not in source
    assert "google.cloud" not in source
    assert "requests" not in source
