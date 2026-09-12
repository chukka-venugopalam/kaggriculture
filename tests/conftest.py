"""Pytest configuration — makes src/kaggriculture importable without an
install step."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "kaggriculture"))
