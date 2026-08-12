#!/usr/bin/env python3
"""Run one explicit SO-101 MuJoCo qualification batch."""

from __future__ import annotations

import sys

from so101_mujoco_demo_py.qualification import main

if __name__ == "__main__":
    sys.exit(main())
