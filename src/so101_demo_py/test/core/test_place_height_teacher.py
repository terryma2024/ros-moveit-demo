"""The Teacher measures the cup tilt and the grasp offset on the executed world (a stable window of fresh evidence) before it
descends to place, and its frozen execution policy is the one the freeze names. What the Teacher does with a measurement outside
the calibration (the fallback target) is in ``test_place_height`` and ``test_teacher_execution``."""

import dataclasses
import math
import re
from types import SimpleNamespace

import pytest

from so101_demo.act.teacher_endpoint import load_teacher_execution_policy
from so101_demo.core import place_height as ph
from so101_demo.core.domain import State
from so101_demo.core.simulation.types import ObjectState
from so101_demo.core.workflow import TERMINAL_STOP_CODES
from so101_demo.ports.evidence import PoseEvidence

from test_b1_teacher_execution import make_adapter
from test_b1_teacher_stop_core import evidence
from paths import PACKAGE_ROOT, TEST_ROOT

PACKAGE = PACKAGE_ROOT
TEACHER_POLICY = PACKAGE / "config/act/teacher_execution_policy.yaml"
HOVER_TARGET_Z = 0.2176344                      # the policy place TCP z (hover); the v1 target is this - 0.01325
CUP_Z, K = 0.1677, 0.037454                     # cup origin height at the hover of the retained bags, TCP above it (measured)


def sample(index, tilt_deg, *, cup_z=CUP_Z):
    half = math.radians(tilt_deg) / 2.0
    state = ObjectState(12, "plastic_cup", (0.02, -0.28, cup_z), (math.sin(half), 0.0, 0.0, math.cos(half)),
                        (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    return dataclasses.replace(evidence(step=1000 + index), object_state=state, simulation_time_s=(1000 + index) * 0.002 * 5,
                               publisher_sequence=1000 + index)


class SteppingObserver:
    """A fresh sample on every snapshot, 10 ms of simulation apart, with the tilt the schedule gives."""

    def __init__(self, tilts, cup_z=CUP_Z):
        self.tilts, self.cup_z, self.count = tilts, cup_z, 0

    def snapshot(self):
        self.count += 1
        tilt = self.tilts(self.count) if callable(self.tilts) else self.tilts
        return sample(self.count, tilt, cup_z=self.cup_z)


def teacher_adapter(tmp_path, tilts=4.04, k=K, cup_z=CUP_Z):
    value = make_adapter(tmp_path)
    value._execution_snapshot_root = PACKAGE
    value._execution_policy = load_teacher_execution_policy(TEACHER_POLICY)
    value.observer = SteppingObserver(tilts, cup_z)
    value._motion_planning_start = lambda: ()
    value._ik = SimpleNamespace(forward=lambda _joints: PoseEvidence((0.0, 0.0, cup_z + k), (0.0, 0.0, 0.0, 1.0)))
    return value


def hover_target():
    return PoseEvidence((-0.0803, -0.2468, HOVER_TARGET_Z), (0.0, 0.0, 0.0, 1.0))


def test_the_tilt_window_is_100_ms_of_simulation_and_other_states_are_untouched(tmp_path):
    value = teacher_adapter(tmp_path)
    theta, k = value._measure_place_height()
    assert (theta, k) == (pytest.approx(math.radians(4.04), abs=1e-9), pytest.approx(K, abs=1e-9))
    assert value.observer.count == 11, "ten 10 ms steps close the first 100 ms window"
    for state in (State.MOVE_ABOVE_PLACE, State.LIFT, State.DESCEND, State.RETREAT):
        original = hover_target()
        assert value._place_target(state, original) is original
    value._execution_snapshot_root = None
    assert value._place_target(State.DESCEND_TO_PLACE, hover_target()).position_m[2] == HOVER_TARGET_Z, "without frozen inputs nothing moves"


def test_a_drifting_tilt_settles_once_it_holds_still_and_the_median_is_used(tmp_path):
    value = teacher_adapter(tmp_path, tilts=lambda n: 4.40 - 0.04 * n if n < 10 else 4.0)
    theta, _k = value._measure_place_height()
    assert theta == pytest.approx(math.radians(4.0), abs=1e-9)
    assert 19 <= value.observer.count <= 21, "the window closes after ten steady samples, not before"


def test_a_tilt_that_never_settles_is_unstable(tmp_path, monkeypatch):
    monkeypatch.setattr(ph, "STABILITY_TIMEOUT_S", 0.05)
    value = teacher_adapter(tmp_path, tilts=lambda n: 4.04 + (0.2 if n % 2 else -0.2))
    with pytest.raises(ph.PlaceHeightRefused) as refusal:
        value._measure_place_height()
    assert refusal.value.code == ph.TILT_UNSTABLE


def test_the_refusal_codes_are_terminal_stop_codes():
    assert set(ph.REFUSAL_CODES) <= TERMINAL_STOP_CODES and ph.MEASUREMENT_FAILED in ph.REFUSAL_CODES


def _raiser(error):
    def raise_it(*args, **kwargs):
        raise error
    return raise_it


def test_a_stop_with_its_own_terminal_code_keeps_it(tmp_path):
    from so101_demo.ros.teacher_stop import TeacherStop

    value = teacher_adapter(tmp_path)
    value._enforce_safety = _raiser(TeacherStop("TEACHER_USER_STOP"))
    with pytest.raises(TeacherStop) as stop:
        value._place_target(State.DESCEND_TO_PLACE, hover_target())
    assert stop.value.code == "TEACHER_USER_STOP"


def test_k_needs_a_fresh_joint_state(tmp_path):
    max_age = load_teacher_execution_policy(TEACHER_POLICY)["state_max_age_s"]
    value = teacher_adapter(tmp_path)
    value._joint_state_received_monotonic_s = value._now[0] - max_age * 0.5
    value._measure_place_height()
    for received in (value._now[0] - max_age - 0.05, None, value._now[0] + 1.0):
        stale = teacher_adapter(tmp_path)
        stale._joint_state_received_monotonic_s = received
        with pytest.raises(ph.PlaceHeightRefused) as refusal:
            stale._measure_place_height()
        assert refusal.value.code == ph.MEASUREMENT_FAILED


@pytest.mark.parametrize("step_s,count", [(0.0099999, 11), (0.01000005, 11), (0.0100002, 11), (0.0098, 12), (0.012, 10), (0.003, 35)])
def test_the_window_is_at_least_100_ms_whatever_the_evidence_cadence(tmp_path, step_s, count):
    """The window is the newest samples that cover at least 100 ms (minus 1 us), whatever the cadence: the live evidence arrives
    every 12 ms (96 ms or 108 ms, never 100), and a window cut back to at most 100 ms never closed there."""
    value = teacher_adapter(tmp_path)

    class Timed(SteppingObserver):
        def snapshot(self):
            base = super().snapshot()
            return dataclasses.replace(base, simulation_time_s=self.count * step_s, publisher_sequence=self.count)

    value.observer = Timed(4.04)
    value._measure_place_height()
    assert value.observer.count == count


def test_a_window_shorter_than_100_ms_of_samples_is_not_enough(tmp_path, monkeypatch):
    """The 1 s timeout (here 50 ms of wall time) ends a measurement whose samples never cover 100 ms of simulation."""
    monkeypatch.setattr(ph, "STABILITY_TIMEOUT_S", 0.05)
    value = teacher_adapter(tmp_path)

    class Slow(SteppingObserver):
        def snapshot(self):
            base = super().snapshot()
            return dataclasses.replace(base, simulation_time_s=self.count * 1e-7, publisher_sequence=self.count)

    value.observer = Slow(4.04)
    with pytest.raises(ph.PlaceHeightRefused) as refusal:
        value._measure_place_height()
    assert refusal.value.code == ph.TILT_UNSTABLE


def test_the_refusal_says_how_many_samples_over_what_span_with_what_tilt_range(tmp_path, monkeypatch):
    monkeypatch.setattr(ph, "STABILITY_TIMEOUT_S", 0.05)
    value = teacher_adapter(tmp_path, tilts=lambda n: 4.04 + (0.2 if n % 2 else -0.2))
    with pytest.raises(ph.PlaceHeightRefused) as refusal:
        value._measure_place_height()
    detail = str(refusal.value)
    assert re.search(r"samples \d+, simulation span \d+\.\d{3} s, tilt range 0\.4\d+ deg", detail), detail
    assert "latest window" in detail and "widest window" in detail


LIVE_INTERVAL = TEST_ROOT / "data/place_height_measured_tilt_interval.json"


def test_a_live_measurement_interval_that_every_first_round_run_refused_is_now_accepted(tmp_path):
    """Replays the evidence of run 3a7cb058 (MOVE_ABOVE_PLACE finish to the refusal, 91 samples, 12 ms apart, tilt 4.03 deg
    drifting 0.013 deg over 1.09 s) through the real measurement code. The tilt range over any 100 ms there is 0.002 deg, 25 times
    under the criterion; the old window logic refused it, the new one accepts it at the 10th sample."""
    import json

    recorded = json.loads(LIVE_INTERVAL.read_text())
    rows = recorded["samples"]
    assert len(rows) == 91 and {round(rows[i + 1]["sim"] - rows[i]["sim"], 6) for i in range(90)} == {0.012}

    class Replay:
        def __init__(self):
            self.index = 0

        def snapshot(self):
            row = rows[min(self.index, len(rows) - 1)]
            self.index += 1
            state = ObjectState(12, "plastic_cup", (0.02, -0.28, row["z"]), (row["qx"], row["qy"], row["qz"], row["qw"]),
                                (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
            return dataclasses.replace(evidence(step=row["step"]), object_state=state, simulation_time_s=row["sim"],
                                       publisher_sequence=row["seq"])

    value = teacher_adapter(tmp_path, cup_z=rows[0]["z"])
    value.observer = Replay()
    theta, _k = value._measure_place_height()
    assert value.observer.index <= 11
    assert math.degrees(theta) == pytest.approx(4.03, abs=0.01)


def test_a_policy_without_a_place_height_mode_refuses_the_descent_target(tmp_path):
    value = make_adapter(tmp_path)
    value._execution_snapshot_root = tmp_path
    value._execution_policy = {"policy_sha256": "x"}
    with pytest.raises(RuntimeError, match="TEACHER_POLICY_UNAVAILABLE"):
        value._place_target(State.DESCEND_TO_PLACE, hover_target())


def test_the_freeze_names_the_execution_policy_the_teacher_loads(tmp_path):
    value = make_adapter(tmp_path)
    config = tmp_path / "config/act"
    config.mkdir(parents=True)
    (config / TEACHER_POLICY.name).write_bytes(TEACHER_POLICY.read_bytes())
    value._teacher_config_dir = config
    value._teacher_policy_files = {"execution": {}}
    value._document = {}
    value._select_execution_policy()
    assert value._execution_policy["schema_version"] == 3 and value._teacher_run()
    assert value._teacher_policy_files["execution"]["path"].endswith(TEACHER_POLICY.name)
    value._select_execution_policy("missing.yaml")
    assert value._execution_policy is None and value._teacher_config_error.startswith("TEACHER_POLICY_UNAVAILABLE")
