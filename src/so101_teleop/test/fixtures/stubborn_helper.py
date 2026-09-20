#!/usr/bin/env python3
"""A helper that ignores SIGTERM and says so, so a test never measures interpreter startup.

A process can only ignore ``SIGTERM`` once it has run the code that ignores it. A test that signals a
child immediately after ``fork`` therefore tests how fast Python starts, not the escalation contract -
the first attempt at these tests did exactly that and failed for the wrong reason. This helper
installs the dispositions and *then* writes its readiness file, and every test that needs a stubborn
process waits for that file before signalling anything.

Usage: ``stubborn_helper.py <ready-path>``
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import sys
import time


def main() -> int:
    ready = Path(sys.argv[1])
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    ready.write_text(json.dumps({"pid": os.getpid(), "ignoring": ["SIGTERM", "SIGINT"]}) + "\n")
    time.sleep(600)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
