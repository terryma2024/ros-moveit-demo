#!/usr/bin/env python3
"""Source-tree entry point for bounded contact-calibration collection."""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

main = import_module("so101_mujoco_demo_py.contact_calibration_collector").main


if __name__ == "__main__":
    raise SystemExit(main())
