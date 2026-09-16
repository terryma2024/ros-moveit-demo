#!/usr/bin/env python3
"""Long-lived descendant process for L2 orphan/cleanup-window tests."""

import os
import sys
import time


def main() -> int:
    ready = os.environ.get("SO101_E2E_DESCENDANT_READY")
    if ready:
        with open(ready, "w", encoding="utf-8") as stream:
            stream.write(str(os.getpid()) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    while True:
        time.sleep(0.5)


if __name__ == "__main__":
    sys.exit(main())
