"""Recorder round 12 (CP-3423): L2 on L8TrV4E3, 44 rows, INPUT_STALE and DYNAMIC_INITIAL_BOUNDARY_AFTER_FIRST_COMMAND.

Two data-side defects found in the retained telemetry (the pacing problem is in rec12-pacing.md):

1. After the Teacher's reset_complete arrived the initial-boundary search ran on every pass. It deep-copies the retained worlds
   and raw steps: 605 passes, 54 s in total, 89 ms on average and 503 ms at worst (main-thread CPU 67 s against 22 to 30 s in
   the runs before). One pass of 503 ms made the next row's instant older than the joint-state ring could cover: the arm and
   neck rings held 32 samples, which at the 500 Hz controller rate is 64 ms, and the row's sources must lie within 100 ms
   BEFORE its instant. INPUT_STALE followed on the next not-ready pass.
2. Once the first command is out the boundary can never be honest again, yet the search kept running for 87 s and the verdict
   was raised on every pass.
"""
import time
from types import SimpleNamespace

import numpy as np
import pytest

from so101_demo.act.synchronizer import RgbObservationSynchronizer


def loaded_synchronizer(*, rate_hz=500, seconds=3.0, camera_hz=30):
    clock = [0.0]
    sync = RgbObservationSynchronizer(max_age_s=0.1, max_skew_s=0.1, monotonic=lambda: clock[0])
    sync.reset("s")
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    steps = int(seconds * rate_hz)
    for index in range(1, steps + 1):
        stamp = index / rate_hz
        sync.push("arm", "s", stamp, [0.0] * 6)
        sync.push("neck", "s", stamp, 0.0)
        if index % (rate_hz // camera_hz) == 0:
            sync.push("head", "s", stamp, frame)
            sync.push("wrist", "s", stamp, frame)
    return sync, steps / rate_hz


def sampler_ready(sync, at_s):
    from so101_demo.act.synchronizer import source_age_ok_ns, time_ns
    return all(any(source_age_ok_ns(time_ns(at_s), time_ns(stamp), time_ns(sync.max_age_s)) for stamp, _, _ in buffer)
               for buffer in sync.buffers.values())


@pytest.mark.parametrize("behind_s", [0.0, 0.05, 0.2, 0.5, 0.9])
def test_a_row_is_ready_however_late_the_loop_gets_to_it_within_the_ring(behind_s):
    sync, now = loaded_synchronizer()
    # the 100 ms camera window needs a camera frame at or before the instant: the instant is a camera instant
    at_s = round((now - behind_s) * 30) / 30
    assert sampler_ready(sync, at_s), f"a pass {behind_s} s late no longer finds its joint states"


def test_the_camera_rings_keep_their_small_capacity():
    sync, _ = loaded_synchronizer()
    assert sync.buffers["head"].maxlen == 32 and sync.buffers["arm"].maxlen >= 2048


# ---- the initial boundary search ---------------------------------------------------------------------------------------

def data_side(*, first_dispatch, searches):
    from so101_demo.ros.recorder_data_side import RecorderDataSide
    side = RecorderDataSide.__new__(RecorderDataSide)
    side.episode_recorder = SimpleNamespace(capture=SimpleNamespace(started=True))
    side._data_verified_reset = b"{}"
    side._data_first_dispatch_begin_ns = first_dispatch
    side._world_record_cursor = 5
    side._scene_source_binding = SimpleNamespace(physics_adapter=SimpleNamespace(received_max_step=lambda: 100))

    def search():
        searches.append(1)
        return None
    side._capture_native_initial_step = search
    return side


def test_after_the_first_command_the_verdict_is_raised_once_and_the_search_never_runs():
    searches = []
    side = data_side(first_dispatch=1, searches=searches)
    with pytest.raises(RuntimeError, match="AFTER_FIRST_COMMAND"):
        side._step_data_initial_boundary()
    for _ in range(50):
        side._step_data_initial_boundary()      # silent: the reason is already latched
    assert searches == []


def test_an_unchanged_search_is_not_repeated_every_pass_but_still_runs_four_times_a_second():
    searches = []
    side = data_side(first_dispatch=None, searches=searches)
    for _ in range(100):
        side._step_data_initial_boundary()
    assert len(searches) == 1
    side._data_initial_last_at -= 0.3
    side._step_data_initial_boundary()
    assert len(searches) == 2
    side._scene_source_binding.physics_adapter.received_max_step = lambda: 101      # new raw data: searched at once
    side._step_data_initial_boundary()
    assert len(searches) == 3


def test_a_failed_search_settles_the_boundary_and_is_not_retried():
    searches = []
    side = data_side(first_dispatch=None, searches=searches)

    def failing():
        searches.append(1)
        raise ValueError("ENDPOINT_INITIAL_BOUNDARY_INVALID")
    side._capture_native_initial_step = failing
    with pytest.raises(ValueError):
        side._step_data_initial_boundary()
    for _ in range(20):
        side._step_data_initial_boundary()
    assert searches == [1]
