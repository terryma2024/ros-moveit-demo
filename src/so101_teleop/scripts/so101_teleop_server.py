#!/usr/bin/env python3
"""Deprecated Teleop entry point.

The unified service is the only web listener. This script only delegates so an existing
operator habit cannot start a second port.
"""

from __future__ import annotations

import sys

from so101_teleop.unified.main import main

DEPRECATION_NOTICE = "so101_teleop_server.py is deprecated; use so101_unified_web_server.py"


def run() -> int:
    print(DEPRECATION_NOTICE, file=sys.stderr)
    main()
    return 0


if __name__ == "__main__":
    sys.exit(run())
