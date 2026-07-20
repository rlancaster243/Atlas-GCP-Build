"""Pytest configuration for Project Atlas."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DAGS = ROOT / "dags"
for path in (SRC, DAGS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
