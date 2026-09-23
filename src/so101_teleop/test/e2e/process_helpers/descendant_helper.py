#!/usr/bin/env python3
"""Bounded descendant process for L2 orphan/cleanup-window tests."""

import argparse
import os
import sys
import time


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner-root")
    parser.add_argument("--max-lifetime-s", type=float, default=120.0)
    args = parser.parse_args(argv)
    if not 0 < args.max_lifetime_s <= 120:
        parser.error("max lifetime must be in (0, 120] seconds")
    ready = os.environ.get("SO101_E2E_DESCENDANT_READY")
    if ready:
        with open(ready, "w", encoding="utf-8") as stream:
            stream.write(str(os.getpid()) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    deadline = time.monotonic() + args.max_lifetime_s
    while time.monotonic() < deadline:
        time.sleep(min(0.5, max(0, deadline - time.monotonic())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
