#!/usr/bin/env python3
"""Run BodyMocap pure-Python unit tests (no Blender required)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    loader = unittest.TestLoader()
    test_dir = Path(__file__).parent
    # These are executable Blender integration scripts, not unittest modules.
    blender_scripts = {"test_in_blender.py", "test_live_gui.py"}
    suite = unittest.TestSuite()
    for path in sorted(test_dir.glob("test_*.py")):
        if path.name not in blender_scripts:
            suite.addTests(loader.discover(str(test_dir), pattern=path.name))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
