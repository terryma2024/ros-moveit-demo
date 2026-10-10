"""Test-only child that keeps its provision identity alive for the C++ reader."""

import sys
from pathlib import Path

from so101_demo.adapters.act.controller_reservation_provision import (
    write_controller_reservation_provision,
)


key = write_controller_reservation_provision(
    Path(sys.argv[1]), role=sys.argv[2], session_id=sys.argv[3])
sys.stdout.buffer.write(key)
sys.stdout.buffer.flush()
sys.stdin.buffer.read(1)
