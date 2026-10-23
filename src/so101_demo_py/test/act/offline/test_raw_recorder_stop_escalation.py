"""`RawRecorder.stop` escalates when `ros2 bag record` does not react to a SIGINT.

Two installed demo gates lost the signal: the recorder's log ended at "Topics discovery started" and the process neither stopped nor logged
anything for the whole 15 s wait, then was killed (RAW_BAG_CLOSE_TIMEOUT). The stop now re-sends SIGINT every STOP_SIGINT_RESEND_S, adds a
SIGTERM at STOP_SIGTERM_AT_S and kills at STOP_SIGKILL_AT_S, and records what it sent. The child here is a fake, not rosbag."""
import subprocess
import sys
import time
from pathlib import Path

import pytest

from so101_demo.act.offline import raw_recorder as module
from so101_demo.act.offline.raw_recorder import RawRecorder

CHILD = """
import os, signal, sys, time
mode, ready = sys.argv[1], sys.argv[2]
count = [0]
def on_int(signum, frame):
    count[0] += 1
    if mode == "exit_on_first" or (mode == "exit_on_second" and count[0] >= 2):
        sys.exit(0)
def on_term(signum, frame):
    if mode == "exit_on_term":
        sys.exit(0)
signal.signal(signal.SIGINT, on_int)
signal.signal(signal.SIGTERM, on_term)
open(ready, "w").write("ready")
while True:
    time.sleep(0.05)
"""


def recorder_with_child(tmp_path, mode):
    recorder = RawRecorder(tmp_path / "bag", topics=("/x",), core_topics=("/x",), scene_reads=None)
    (tmp_path / "bag").mkdir()
    log_path = tmp_path / "bag-record.log"
    recorder._log = open(log_path, "xb")
    ready = tmp_path / "child-ready"
    recorder._recorder = subprocess.Popen([sys.executable, "-c", CHILD, mode, str(ready)], stdout=recorder._log,
                                          stderr=subprocess.STDOUT, start_new_session=True)
    deadline = time.monotonic() + 10
    while not ready.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert ready.exists()
    recorder.verify_closed = lambda: {"closed": True}        # the fake wrote no bag; the stop path itself is under test
    return recorder, log_path


def test_the_timing_constants_are_named_and_ordered():
    assert 0 < module.STOP_SIGINT_RESEND_S < module.STOP_SIGTERM_AT_S < module.STOP_SIGKILL_AT_S
    assert module.STOP_SIGKILL_AT_S == 15.0 and module.STOP_SIGTERM_AT_S == 8.0 and module.STOP_SIGINT_RESEND_S == 2.0
    assert module.STOP_LOG_TAIL_BYTES == 4096


def test_a_child_that_exits_on_the_first_sigint_returns_what_it_always_did(tmp_path):
    recorder, _log = recorder_with_child(tmp_path, "exit_on_first")
    began = time.monotonic()
    stats = recorder.stop()
    assert time.monotonic() - began < module.STOP_SIGINT_RESEND_S
    assert stats["closed"] is True and stats["failure"] is None and stats["bag_process_rc"] == 0
    assert "stop_signals" not in stats and "stop_log_tail" not in stats


def test_a_child_that_ignores_the_first_sigint_and_exits_on_the_second_is_closed_in_time(tmp_path):
    recorder, _log = recorder_with_child(tmp_path, "exit_on_second")
    began = time.monotonic()
    stats = recorder.stop()
    elapsed = time.monotonic() - began
    assert elapsed < 6.0, elapsed
    assert stats["closed"] is True and stats["failure"] is None and stats["bag_process_rc"] == 0, stats
    assert [item["signal"] for item in stats["stop_signals"]] == ["SIGINT", "SIGINT"]
    assert stats["stop_signals"][1]["at_s"] >= module.STOP_SIGINT_RESEND_S - 0.1


def test_a_child_that_ignores_sigint_and_sigterm_is_killed_with_the_signals_and_the_log_tail_recorded(tmp_path, monkeypatch):
    # the same ordering with small values, so that the test does not wait 15 s; the code reads the module constants at call time
    monkeypatch.setattr(module, "STOP_SIGINT_RESEND_S", 0.2)
    monkeypatch.setattr(module, "STOP_SIGTERM_AT_S", 0.8)
    monkeypatch.setattr(module, "STOP_SIGKILL_AT_S", 1.5)
    recorder, log_path = recorder_with_child(tmp_path, "ignore_all")
    recorder._log.write(b"x" * 10000 + b"LAST-LINE\n")
    recorder._log.flush()
    stats = recorder.stop()
    assert stats["failure"] == "RAW_BAG_CLOSE_TIMEOUT"
    names = [item["signal"] for item in stats["stop_signals"]]
    assert names[0] == "SIGINT" and "SIGTERM" in names and names[-1] == "SIGKILL" and names.count("SIGTERM") == 1
    assert all(later["at_s"] >= earlier["at_s"] for earlier, later in zip(stats["stop_signals"], stats["stop_signals"][1:]))
    assert 0 < len(stats["stop_log_tail"].encode()) <= module.STOP_LOG_TAIL_BYTES and stats["stop_log_tail"].rstrip().endswith("LAST-LINE")
    assert recorder._recorder is None
