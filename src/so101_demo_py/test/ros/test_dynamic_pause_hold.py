"""The execution consumer starts while the parent still freezes the simulation for the inference hold, so a paused frame of the
expected session and epoch is an owned hold, bounded in time, not an identity violation. A frame of another epoch, a hold that
outlasts the bound and every other identity breach still fail, and the failure names the frame it saw."""

import json
from dataclasses import replace

import pytest

from so101_demo.backends.mujoco.observer import EvidenceStale
from so101_demo.core.domain import State
from so101_demo.core.simulation.types import ReceivedSimulationEvidence
from so101_demo.ros import dynamic_mujoco_execution as module

from test_teacher_moveit_execution import make_adapter
from test_teacher_stop_flags_and_cup_safety import evidence

CODE = "DYNAMIC_RESET_EPOCH_MISMATCH"
DETAIL_KEYS = {"paused", "reset_epoch", "expected_reset_epoch", "simulation_step", "publisher_sequence", "receive_age_s", "recent"}


class FramesObserver:
    """Serves the frames in order (the last one repeats) and keeps the history the real observer keeps."""

    def __init__(self, clock, frames):
        self.clock, self.frames, self.index, self.seen = clock, list(frames), 0, []

    def _next(self):
        frame = self.frames[min(self.index, len(self.frames) - 1)]
        self.index += 1
        self.seen.append(frame)
        return frame

    def snapshot(self):
        return self._next()

    def snapshot_with_receipt(self):
        return ReceivedSimulationEvidence(self._next(), self.clock())

    def recent_summaries(self, limit=5):
        return [{"paused": f.paused, "reset_epoch": f.reset_epoch, "simulation_step": f.simulation_step,
                 "publisher_sequence": f.publisher_sequence, "age_s": 0.01 * (len(self.seen) - i)}
                for i, f in enumerate(self.seen)][-limit:]


def frame(step, **change):
    return replace(evidence(step=step), **change)


def adapter(tmp_path, frames):
    value = make_adapter(tmp_path)
    value.observer = FramesObserver(lambda: value._now[0], frames)
    value._wait_progress = lambda: value._now.__setitem__(0, value._now[0] + 0.01)
    return value


@pytest.fixture()
def clock(monkeypatch):
    now = [1000.0]

    def monotonic():
        now[0] += 0.05
        return now[0]
    monkeypatch.setattr(module.time, "monotonic", monotonic)
    return now


def detail(error):
    text = str(error.value)
    assert text.startswith(CODE + ": "), text
    return json.loads(text[len(CODE) + 2:])


def test_snapshot_failure_names_the_frame_it_saw(tmp_path, clock):
    value = adapter(tmp_path, [frame(101, reset_epoch=2)])
    with pytest.raises(RuntimeError) as error:
        value._snapshot()
    seen = detail(error)
    assert DETAIL_KEYS <= set(seen)
    assert (seen["paused"], seen["reset_epoch"], seen["expected_reset_epoch"], seen["simulation_step"]) == (False, 2, 1, 101)
    assert [item["simulation_step"] for item in seen["recent"]] == [101]


def test_monitor_failure_names_the_frame_it_saw(tmp_path):
    value = adapter(tmp_path, [frame(100, reset_epoch=2)])
    with pytest.raises(RuntimeError) as error:
        value._motion_monitor(State.MOVE_ABOVE_PLACE)()
    seen = detail(error)
    assert DETAIL_KEYS <= set(seen) and seen["reset_epoch"] == 2 and seen["expected_reset_epoch"] == 1


def test_snapshot_waits_through_a_hold_for_a_running_frame(tmp_path, clock):
    value = adapter(tmp_path, [frame(100, paused=True), frame(100, paused=True), frame(130)])
    assert value._snapshot().simulation_step == 130


def test_snapshot_fails_when_the_hold_outlasts_the_bound(tmp_path, clock):
    value = adapter(tmp_path, [frame(100, paused=True)])
    with pytest.raises(RuntimeError) as error:
        value._snapshot()
    seen = detail(error)
    assert seen["paused"] is True and seen["simulation_step"] == 100


def test_snapshot_does_not_wait_for_another_epoch(tmp_path, clock):
    value = adapter(tmp_path, [frame(100, reset_epoch=2, paused=True), frame(130)])
    with pytest.raises(RuntimeError, match=CODE):
        value._snapshot()
    assert value.observer.index == 1


def test_monitor_skips_a_held_sample_and_resumes_when_the_world_runs(tmp_path):
    value = adapter(tmp_path, [frame(100, paused=True), frame(100, paused=True), frame(130)])
    monitor = value._motion_monitor(State.MOVE_ABOVE_PLACE)
    monitor()
    value._now[0] += 0.4
    value._joint_state_received_monotonic_s = value._now[0]
    monitor()
    value._now[0] += 0.4
    value._joint_state_received_monotonic_s = value._now[0]
    monitor()                                    # running frame: no failure, and the hold timer restarts
    value.observer.frames = [frame(131, paused=True)]
    value.observer.index = 0
    value._now[0] += 0.9
    value._joint_state_received_monotonic_s = value._now[0]
    monitor()                                    # a new hold starts here, not 1.7 s ago


def test_monitor_fails_when_the_hold_outlasts_state_unavailable_stop(tmp_path):
    value = adapter(tmp_path, [frame(100, paused=True)])
    monitor = value._motion_monitor(State.MOVE_ABOVE_PLACE)
    monitor()
    value._now[0] += 0.9
    value._joint_state_received_monotonic_s = value._now[0]
    monitor()                                    # 0.9 s into the hold: tolerated
    value._now[0] += 0.2
    value._joint_state_received_monotonic_s = value._now[0]
    with pytest.raises(RuntimeError) as error:
        monitor()
    assert detail(error)["paused"] is True


def test_a_hold_in_the_session_check_order_still_fails_on_another_session(tmp_path):
    value = adapter(tmp_path, [frame(100, paused=True, simulation_session_id="other")])
    with pytest.raises(RuntimeError, match="DYNAMIC_SESSION_MISMATCH"):
        value._motion_monitor(State.MOVE_ABOVE_PLACE)()
