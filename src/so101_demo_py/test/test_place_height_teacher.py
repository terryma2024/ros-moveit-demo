"""CP-3480 / CP-3394: the Teacher computes the DESCEND_TO_PLACE target from the measured cup tilt (policy v2), refuses outside the
calibration with a terminal stop and leaves the cup held, and a freeze can bind either execution policy."""

import dataclasses
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.act.teacher_endpoint import load_teacher_execution_policy
from so101_demo.core import place_height as ph
from so101_demo.core.domain import ActionStatus, State
from so101_demo.core.simulation.types import ObjectState
from so101_demo.core.workflow import TERMINAL_STOP_CODES, resolve_transition
from so101_demo.ports.evidence import PoseEvidence

from test_b1_teacher_execution import make_adapter
from test_b1_teacher_stop_core import evidence

PACKAGE = Path(__file__).resolve().parents[1]
V2 = PACKAGE / "config/act/teacher_execution_policy_v2.yaml"
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


def v2_adapter(tmp_path, tilts=4.04, k=K, cup_z=CUP_Z):
    value = make_adapter(tmp_path)
    value._execution_snapshot_root = PACKAGE
    value._teacher_execution_policy = load_teacher_execution_policy(V2)
    value.observer = SteppingObserver(tilts, cup_z)
    value._motion_planning_start = lambda: ()
    value._ik = SimpleNamespace(forward=lambda _joints: PoseEvidence((0.0, 0.0, cup_z + k), (0.0, 0.0, 0.0, 1.0)))
    return value


def hover_target():
    return PoseEvidence((-0.0803, -0.2468, HOVER_TARGET_Z), (0.0, 0.0, 0.0, 1.0))


def test_the_measured_tilt_and_grasp_offset_give_the_target_and_the_audit_document(tmp_path):
    value = v2_adapter(tmp_path)
    target = value._place_target(State.DESCEND_TO_PLACE, hover_target())
    document = value._document["place_height"]
    policy = load_teacher_execution_policy(V2)
    expected = ph.target_tcp_z(math.radians(4.04), K, ph.cup_geometry_from_scene(PACKAGE / "assets/mujoco/act/scene.xml"),
                               ph.PlaceHeightPolicy.from_document(policy))
    assert target.position_m == (-0.0803, -0.2468, pytest.approx(expected, abs=1e-9)) and target.orientation_xyzw == (0.0, 0.0, 0.0, 1.0)
    assert document["tilt_rad"] == pytest.approx(math.radians(4.04), abs=1e-9) and document["grasp_offset_m"] == pytest.approx(K, abs=1e-9)
    assert document["guard_m"] == policy["place_touchdown_guard_m"] and document["target_tcp_z_m"] == pytest.approx(expected, abs=1e-12)
    ph.validate_document(document, ph.PlaceHeightPolicy.from_document(policy))
    assert 0.0 < target.position_m[2] - (HOVER_TARGET_Z - 0.01325) < 0.003


def test_the_tilt_window_is_100_ms_of_simulation_and_other_states_are_untouched(tmp_path):
    value = v2_adapter(tmp_path)
    value._place_target(State.DESCEND_TO_PLACE, hover_target())
    assert value.observer.count == 11, "ten 10 ms steps close the first 100 ms window"
    for state in (State.MOVE_ABOVE_PLACE, State.LIFT, State.DESCEND, State.RETREAT):
        original = hover_target()
        assert value._place_target(state, original) is original
    value._execution_snapshot_root = None
    assert value._place_target(State.DESCEND_TO_PLACE, hover_target()).position_m[2] == HOVER_TARGET_Z, "without frozen inputs nothing moves"


def test_a_drifting_tilt_settles_once_it_holds_still_and_the_median_is_used(tmp_path):
    value = v2_adapter(tmp_path, tilts=lambda n: 4.40 - 0.04 * n if n < 10 else 4.0)
    value._place_target(State.DESCEND_TO_PLACE, hover_target())
    assert value._document["place_height"]["tilt_rad"] == pytest.approx(math.radians(4.0), abs=1e-9)
    assert 19 <= value.observer.count <= 21, "the window closes after ten steady samples, not before"


def test_a_tilt_that_never_settles_is_refused_unstable(tmp_path, monkeypatch):
    monkeypatch.setattr(ph, "STABILITY_TIMEOUT_S", 0.05)
    value = v2_adapter(tmp_path, tilts=lambda n: 4.04 + (0.2 if n % 2 else -0.2))
    with pytest.raises(ph.PlaceHeightRefused) as refusal:
        value._place_target(State.DESCEND_TO_PLACE, hover_target())
    assert refusal.value.code == ph.TILT_UNSTABLE and value._document["place_height"]["refused"] == ph.TILT_UNSTABLE


@pytest.mark.parametrize("tilts,k,code", [
    (2.0, K, ph.TILT_OUT_OF_RANGE), (7.0, K, ph.TILT_OUT_OF_RANGE), (4.04, K + 0.002, ph.HEIGHT_OUT_OF_BOUNDS),
    (4.04, K - 0.002, ph.HEIGHT_OUT_OF_BOUNDS)])
def test_a_measurement_outside_the_calibration_is_refused(tmp_path, tilts, k, code):
    value = v2_adapter(tmp_path, tilts=tilts, k=k)
    with pytest.raises(ph.PlaceHeightRefused) as refusal:
        value._place_target(State.DESCEND_TO_PLACE, hover_target())
    assert refusal.value.code == code and value._document["place_height"]["refused"] == code


@pytest.mark.parametrize("tilts,k,code", [
    (2.0, K, ph.TILT_OUT_OF_RANGE), (4.04, K + 0.002, ph.HEIGHT_OUT_OF_BOUNDS), ("unstable", K, ph.TILT_UNSTABLE)])
def test_a_refusal_ends_the_run_with_the_cup_held_and_a_stopped_safety_outcome(tmp_path, monkeypatch, tilts, k, code):
    """No goal, no gripper command, no phase: the failure is a terminal stop (ERROR, no RECOVER_* chain, so nothing opens the
    gripper) and the Teacher status is STOPPED_SAFETY."""
    if tilts == "unstable":
        monkeypatch.setattr(ph, "STABILITY_TIMEOUT_S", 0.05)
        tilts = lambda n: 4.04 + (0.2 if n % 2 else -0.2)       # noqa: E731
    value = v2_adapter(tmp_path, tilts=tilts, k=k)
    forbidden = []
    for name in ("_motion", "_command_gripper", "_phase_open", "_open_supported_gripper", "_attach", "_detach_or_sync"):
        setattr(value, name, lambda *a, _n=name, **kw: forbidden.append(_n))
    value._phase_finish = lambda *a, **kw: None
    value._write = lambda: None
    result = value._perform_state(State.DESCEND_TO_PLACE, hover_target())
    assert forbidden == [] and result.status is ActionStatus.FAILED and result.failure.code == code
    assert code in TERMINAL_STOP_CODES
    assert resolve_transition(State.DESCEND_TO_PLACE, result.status, result.failure) is State.ERROR
    assert type(value)._teacher_execution_status(result, {}) == "STOPPED_SAFETY"


def test_the_three_refusal_codes_are_terminal_stop_codes():
    assert set(ph.REFUSAL_CODES) <= TERMINAL_STOP_CODES


def test_v1_keeps_the_constant_offset_and_a_policy_without_either_refuses(tmp_path):
    value = make_adapter(tmp_path)
    value._execution_snapshot_root = tmp_path
    assert value._place_target(State.DESCEND_TO_PLACE, hover_target()).position_m[2] == pytest.approx(HOVER_TARGET_Z - 0.01325)
    value._teacher_execution_policy = {"policy_sha256": "x"}
    with pytest.raises(RuntimeError, match="TEACHER_POLICY_UNAVAILABLE"):
        value._place_target(State.DESCEND_TO_PLACE, hover_target())


def test_the_freeze_names_the_execution_policy_the_teacher_loads(tmp_path):
    value = make_adapter(tmp_path)
    config = tmp_path / "config/act"
    config.mkdir(parents=True)
    for name in ("teacher_execution_policy_v1.yaml", "teacher_execution_policy_v2.yaml"):
        (config / name).write_bytes((PACKAGE / "config/act" / name).read_bytes())
    value._teacher_config_dir = config
    value._teacher_policy_files = {"execution": {}}
    value._select_execution_policy("teacher_execution_policy_v2.yaml")
    assert value._teacher_execution_policy["schema_version"] == 2 and value._teacher_policy_files["execution"]["path"].endswith("_v2.yaml")
    value._select_execution_policy("teacher_execution_policy_v1.yaml")
    assert value._teacher_execution_policy["place_descend_offset_m"] == -0.01325
    value._select_execution_policy("missing.yaml")
    assert value._teacher_execution_policy is None and value._teacher_config_error.startswith("TEACHER_POLICY_UNAVAILABLE")
