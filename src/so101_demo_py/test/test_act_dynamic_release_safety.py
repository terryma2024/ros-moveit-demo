"""The actual dynamic child may open only on fresh, stopped, supported authorization."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.core.domain import State, ActionStatus
from so101_demo.core.simulation.types import ContactEvidence, ObjectState, SimulationEvidence, ReceivedSimulationEvidence
from so101_demo.act.teacher_endpoint import load_teacher_execution_policy
from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution

EXECUTION_POLICY = Path(__file__).resolve().parents[1] / "config/act/teacher_execution_policy_v1.yaml"


def world(*, step=501, sequence=6, supported=True, bilateral=True):
    def contact(other, geom):
        return ContactEvidence(1, 1, "plastic_cup", "cup_wall", 2, 2, other, geom,
                               (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 0.001, 0.5)
    return SimulationEvidence(
        simulation_time_s=step * 0.002, frame_id="world", publisher_sequence=sequence,
        simulation_step=step, reset_epoch=1, simulation_session_id="s", paused=False,
        object_state=ObjectState(1, "plastic_cup", (0.02, -0.28, 0.165), (0.0, 0.0, 0.0, 1.0),
                                 (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        has_contact=True, minimum_signed_distance_m=0.001, maximum_normal_force_n=0.5,
        truncated=False,
        left_fingertip_contacts=(contact("gripper", "left_tip"),) if bilateral else (),
        right_fingertip_contacts=(contact("jaw", "right_tip"),) if bilateral else (),
        other_object_contacts=(contact("table", "table_collision"),) if supported else ())


def _observer(recent):
    return SimpleNamespace(recent_with_receipts=recent, snapshot_with_receipt=lambda: ReceivedSimulationEvidence(
        world(step=500, sequence=5), 10.0))


def boundary(*, change="positive", clock=10.05):
    value = object.__new__(RosDynamicMujocoExecution)
    now = [clock]
    baseline = world(step=500, sequence=5)
    selected = world(supported=change != "unsupported", bilateral=change != "unilateral")
    receipt = 9.8 if change == "stale" else 10.02
    if change == "prestop":
        selected = baseline
    elif change == "foreign_epoch":
        selected = replace(selected, reset_epoch=2)
    elif change == "zero_force":
        selected = replace(selected, other_object_contacts=tuple(
            replace(item, normal_force_n=0.0) for item in selected.other_object_contacts))
    value._session_id, value._expected_reset_epoch = "s", 1
    # The release freshness bound is the Teacher execution policy's state_max_age_s (0.5 s). The ACT rgb_sync age is
    # deliberately absent from this policy: nothing in the release path may read it.
    value._release_runtime_policy = {"safety_release": {"support_distance_max_m": 0.002}}
    value._teacher_execution_policy = load_teacher_execution_policy(EXECUTION_POLICY)
    value._monotonic = lambda: now[0]
    value._progress = lambda: now.__setitem__(0, now[0] + 0.005)
    value._snapshot = lambda: baseline
    value.observer = _observer(lambda: (
        ReceivedSimulationEvidence(baseline, 10.0), ReceivedSimulationEvidence(selected, receipt)))
    # B1: no broker. The stop proof is the preceding ExecuteTrajectory result plus fresh joint states below the stop velocity.
    value._attempt_id = "a"
    value._last_arm_result = "SUCCEEDED"
    value._positions = {name: 0.1 for name in ("1", "2", "3", "4", "5", "6")}
    value._joint_velocities = {name: (0.01 if change == "stop_unconfirmed" else 0.0) for name in value._positions}
    value._joint_state_received_monotonic_s = 10.01
    value.observer.snapshot_with_receipt = lambda: ReceivedSimulationEvidence(baseline, 10.0)
    value._document = {}
    value._write = lambda: None
    value._attached = True
    value._release_authorization = None
    commands = []
    value._command_gripper = lambda *args, **kwargs: commands.append((args, kwargs))
    value._confirm_detached_shadow = lambda: True
    from so101_demo.adapters.act.scene_state import SceneStateObserver
    value._scene_source_observer = SceneStateObserver(
        model_sha256="a" * 64, nq=1, nv=1, max_age_s=0.5,
        monotonic=lambda: value._monotonic())
    value._scene_source_observer.reset("s", 1, source_floor_s=0.0)
    for step in (501, 502, 503):
        value._scene_source_observer.accept({
            "simulation_session_id": "s", "reset_epoch": 1, "simulation_step": step,
            "paused": False, "simulation_time_s": step * 0.002, "model_sha256": "a" * 64,
            "qpos": [0.0], "qvel": [0.0],
            "clock_interval_begin_monotonic_ns": 10_019_000_000 + (step - 501) * 2_000_000,
            "clock_interval_end_monotonic_ns": 10_020_000_000 + (step - 501) * 2_000_000})
    return value, selected, commands


@pytest.mark.parametrize("change", ["positive", "unsupported", "unilateral", "zero_force",
                                   "prestop", "stale", "foreign_epoch", "stop_unconfirmed"])
def test_actual_child_preflight_rejects_unsupported_or_unproven_source(change):
    value, selected, commands = boundary(change=change)
    if change == "positive":
        assert value._supported_release_preflight() == selected
    else:
        with pytest.raises(RuntimeError):
            value._supported_release_preflight()
        assert value._release_authorization is None
    assert commands == []


def test_first_generated_post_stop_source_is_not_skipped_for_later_rpc_epoch_measurement():
    value, selected, commands = boundary()
    proof = value._normal_stop_proof()
    assert value._first_source_after_stop(proof, previous_step=500, previous_sequence=5) == selected
    assert value._selected_release_source.evidence.simulation_step == 501
    assert commands == []


@pytest.mark.parametrize("state", [State.OPEN_GRIPPER])  # RECOVER_OPEN_GRIPPER: test_b1_teacher_execution.py
def test_actual_child_open_routes_require_preflight_before_any_command(state):
    value, _, commands = boundary()
    value._attached = False
    with pytest.raises(RuntimeError, match="DYNAMIC_RELEASE_PREFLIGHT_REQUIRED"):
        value._open_supported_gripper(state)
    assert commands == []


@pytest.mark.parametrize("state", [State.OPEN_GRIPPER, State.RECOVER_OPEN_GRIPPER])
def test_actual_child_perform_open_cannot_bypass_supported_authorization(state):
    value, selected, commands = boundary(change="unsupported")
    value._initial = selected
    value._attached = False
    result = value.perform(state, None)
    assert result.status is ActionStatus.FAILED
    assert commands == []


def test_actual_child_open_consumes_authorization_and_rechecks_support_after_detach():
    value, selected, commands = boundary()
    value._supported_release_preflight()
    value._attached = False
    selected = world(step=502, sequence=7)
    value.observer = _observer(lambda: (
        ReceivedSimulationEvidence(selected, 10.03),))
    value._open_supported_gripper(State.OPEN_GRIPPER)
    assert len(commands) == 1
    assert commands[0][1]["before"] == selected
    with pytest.raises(RuntimeError, match="DYNAMIC_RELEASE_PREFLIGHT_REQUIRED"):
        value._open_supported_gripper(State.OPEN_GRIPPER)
    assert len(commands) == 1


def test_actual_child_support_lost_after_detach_never_dispatches_open():
    value, _, commands = boundary()
    value._supported_release_preflight()
    value._attached = False
    lost = world(step=502, sequence=7, supported=False)
    value.observer = _observer(lambda: (ReceivedSimulationEvidence(lost, 10.03),))
    with pytest.raises(RuntimeError, match="DYNAMIC_RELEASE_SUPPORT_NOT_PROVED"):
        value._open_supported_gripper(State.OPEN_GRIPPER)
    assert commands == [] and value._release_authorization is None


def test_actual_child_does_not_skip_first_eligible_unsupported_source_for_a_later_good_one():
    value, _, commands = boundary()
    value._supported_release_preflight()
    value._attached = False
    value.observer = _observer(lambda: (
        ReceivedSimulationEvidence(world(step=502, sequence=7, supported=False), 10.03),
        ReceivedSimulationEvidence(world(step=503, sequence=8), 10.04)))
    with pytest.raises(RuntimeError, match="DYNAMIC_RELEASE_SUPPORT_NOT_PROVED"):
        value._open_supported_gripper(State.OPEN_GRIPPER)
    assert commands == []


def test_selected_release_source_expiring_during_write_cannot_dispatch_open():
    value, _, commands = boundary()
    value._supported_release_preflight()
    value._attached = False
    value.observer = _observer(lambda: (
        ReceivedSimulationEvidence(world(step=502, sequence=7), 10.03),))
    now = [10.05]
    value._monotonic = lambda: now[0]
    value._write = lambda: now.__setitem__(0, 10.54)  # 0.51 s after the selected 10.03 receipt
    with pytest.raises(RuntimeError, match="DYNAMIC_RELEASE_SOURCE_EXPIRED"):
        value._open_supported_gripper(State.OPEN_GRIPPER)
    assert commands == []


def test_delayed_pre_stop_production_cannot_be_authorized_by_post_stop_receipt():
    value, selected, commands = boundary()
    scene = value._scene_source_observer
    with scene._lock:
        # The delayed world receipt is 10.02 but the actual producer interval predates stop 10.01.
        scene._history[0][0]["clock_interval_begin_monotonic_ns"] = 10_005_000_000
        scene._history[0][0]["clock_interval_end_monotonic_ns"] = 10_006_000_000
    with pytest.raises(RuntimeError, match="DYNAMIC_RELEASE_POST_STOP_SOURCE_UNAVAILABLE"):
        value._supported_release_preflight()
    assert commands == [] and value._release_authorization is None


def test_release_without_actual_source_clock_cannot_use_receipt_as_generation_proof():
    value, _, commands = boundary()
    value._scene_source_observer = None
    with pytest.raises(RuntimeError, match="DYNAMIC_RELEASE_SOURCE_CLOCK_REQUIRED"):
        value._supported_release_preflight()
    assert commands == [] and value._release_authorization is None


def test_first_unassociated_candidate_expiring_cannot_be_replaced_by_a_later_associated_one():
    from so101_demo.adapters.act.scene_state import SceneStateObserver

    value, first, commands = boundary()
    now = [10.05]
    value._monotonic = lambda: now[0]
    scene = SceneStateObserver(model_sha256="a" * 64, nq=1, nv=1, max_age_s=0.5,
                               monotonic=lambda: now[0])
    scene.reset("s", 1, source_floor_s=0.0)
    value._scene_source_observer = scene
    later = world(step=503, sequence=8)
    value.observer = _observer(lambda: (
        (ReceivedSimulationEvidence(first, 10.02),) if now[0] < 10.525 else
        (ReceivedSimulationEvidence(later, now[0]),)))

    def progress():
        now[0] += 0.005
        if now[0] >= 10.525 and scene.last is None:
            assert scene.accept({
                "simulation_session_id": "s", "reset_epoch": 1, "simulation_step": 503,
                "paused": False, "simulation_time_s": 1.006, "model_sha256": "a" * 64,
                "qpos": [0.0], "qvel": [0.0],
                "clock_interval_begin_monotonic_ns": round((now[0] - 0.001) * 1e9),
                "clock_interval_end_monotonic_ns": round(now[0] * 1e9)})

    value._progress = progress
    with pytest.raises(RuntimeError, match="DYNAMIC_RELEASE_SOURCE_EXPIRED"):
        value._supported_release_preflight()
    assert commands == [] and value._release_authorization is None


def test_release_bounds_are_the_teacher_state_age_and_the_support_distance():
    value, _, _ = boundary()
    assert value._release_bounds() == (0.5, 0.002)


@pytest.mark.parametrize("policy", [None, {}, {"state_max_age_s": 0.0}, {"state_max_age_s": float("nan")},
                                    {"state_max_age_s": "0.5"}])
def test_release_bounds_refuse_a_missing_or_unusable_teacher_state_age(policy):
    value, _, _ = boundary()
    value._teacher_execution_policy = policy
    with pytest.raises(RuntimeError, match="DYNAMIC_RELEASE_POLICY_INVALID"):
        value._release_bounds()


def test_release_preflight_accepts_a_post_stop_source_up_to_the_teacher_state_age():
    """A source 0.33 s old is stale for the 100 ms ACT contract and fresh for the 0.5 s Teacher policy."""
    value, selected, commands = boundary(clock=10.35)
    assert value._supported_release_preflight() == selected
    assert value._release_authorization is not None and commands == []


def test_release_preflight_refuses_a_source_older_than_the_teacher_state_age():
    value, _, commands = boundary(clock=10.60)
    with pytest.raises(RuntimeError, match="DYNAMIC_NORMAL_STOP_UNCONFIRMED"):
        value._supported_release_preflight()
    assert commands == [] and value._release_authorization is None


def test_release_preflight_still_requires_the_source_to_be_generated_after_the_stop_at_the_wider_bound():
    value, _, commands = boundary(change="prestop", clock=10.35)
    with pytest.raises(RuntimeError, match="DYNAMIC_RELEASE_POST_STOP_SOURCE_UNAVAILABLE"):
        value._supported_release_preflight()
    assert commands == [] and value._release_authorization is None


