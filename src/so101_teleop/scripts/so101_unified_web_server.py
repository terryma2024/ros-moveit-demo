#!/usr/bin/env python3
"""Installed entry point: the single unified web service."""

from __future__ import annotations

import sys

from so101_teleop.unified.main import main


def run() -> int:
    main()
    return 0


if __name__ == "__main__":
    sys.exit(run())
