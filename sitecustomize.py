"""Repo-local Python bootstrap for source runs and test isolation."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"

if SRC.exists():
    src_str = str(SRC)
    if src_str not in sys.path:
        sys.path.insert(0, src_str)

# Keep pytest isolated from unrelated global plugins installed on the machine.
os.environ.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
