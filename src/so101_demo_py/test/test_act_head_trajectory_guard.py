"""Directed numeric and real MuJoCo fixtures for the file-v1 Head guard."""

from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
from types import SimpleNamespace

import mujoco
import numpy as np
import pytest

from head_admission_peer_support import admission_peer_cpu_slot, release_guard_buffers

from so101_demo.act.head_evidence_identity import canonical_bytes
from so101_demo.adapters.act.head_trajectory_guard import (
    HeadTrajectoryGuard, _Snapshot, quintic_extrema,
)
from so101_demo.adapters.act.physics import model_sha256
from so101_demo.adapters.act.pick_place_neck_sweep import MujocoNeckSweepChecker
from control_msgs.action import FollowJointTrajectory
from trajectory_msgs.msg import JointTrajectoryPoint


REPOSITORY = Path(os.environ.get(
    "SO101_HFP_REPOSITORY", "/data/work/ws_moveit/.worktrees/so101-head-file-protocol-1003"
))
MODEL = REPOSITORY / "src/so101_demo_py/assets/mujoco/act/head_search_scene.xml"
GEOMETRY = Path(
    "/data/work/so101-evidence/act-data/20260930-antzb-head-search-krIv681m/"
    "head-file-protocol-1003/head-camera-yolo-sampling-20261009-001/"
    "geometry-new/head-camera-geometry.json"
)
GEOMETRY_SHA256 = "f0f04d0e4519a13f9657de6f1bd2bab5b4443c0f935360968c1cee2eb6fad72a"
MODEL_XML_SHA256 = "aea2df3b0bfb608d7d3aec2e58cd8f45b51affd8bf92511de5e99475fcc47f14"
MODEL_SEMANTIC_SHA256 = "970546aa5354add3b744fe027905f45a4477ae10bc7db3d4f7862a9bf05359b7"


class _Scene:
    def __init__(self, semantic_sha):
        self.model_sha256 = semantic_sha
        self.max_age = .25

    def snapshot_with_receipt(self):
        raise AssertionError("collision-only tests do not read scene state")


@pytest.fixture
def guard(tmp_path_factory):
    with admission_peer_cpu_slot(tmp_path_factory):
        assembled = _assemble_guard()
    try:
        yield assembled
    finally:
        release_guard_buffers(assembled, owns_model=True)


def _assemble_guard():
    assert hashlib.sha256(MODEL.read_bytes()).hexdigest() == MODEL_XML_SHA256
    assert hashlib.sha256(GEOMETRY.read_bytes()).hexdigest() == GEOMETRY_SHA256
    pristine = mujoco.MjModel.from_xml_path(str(MODEL))
    semantic = model_sha256(pristine)
    assert semantic == MODEL_SEMANTIC_SHA256
    checker = MujocoNeckSweepChecker(MODEL,
        expected_model_sha256=semantic, protected_roots=("base",),
        allowed_pairs=(), path_step_s=.002, path_clearance_m=.001,
        max_samples=50000)
    return HeadTrajectoryGuard(checker=checker,
        feedback_port=SimpleNamespace(feedback_snapshot=lambda: None),
        scene_observer=_Scene(semantic),
        node=SimpleNamespace(get_clock=lambda: SimpleNamespace(
            now=lambda: SimpleNamespace(nanoseconds=1_000_000_000))),
        model_xml_path=MODEL, geometry_path=GEOMETRY,
        geometry_sha256=GEOMETRY_SHA256,
        simulation_session_id="fixture-scene", reset_epoch=1)


def snapshot_for(guard, *, neck, bottle_pose=None):
    data = mujoco.MjData(guard._model)
    for name, value in zip(("1", "2", "3", "4", "5", "6"),
                           (-.25, 0., .6, .8, 0., .8), strict=True):
        joint = mujoco.mj_name2id(guard._model, mujoco.mjtObj.mjOBJ_JOINT, name)
        data.qpos[guard._model.jnt_qposadr[joint]] = value
    neck_joint = mujoco.mj_name2id(guard._model, mujoco.mjtObj.mjOBJ_JOINT,
                                   "neck_yaw_joint")
    data.qpos[guard._model.jnt_qposadr[neck_joint]] = neck
    if bottle_pose is not None:
        data.qpos[21:28] = (*bottle_pose, 1., 0., 0., 0.)
    mujoco.mj_fwdPosition(guard._model, data)
    return _Snapshot(scope=canonical_bytes({"fixture": "collision"}),
        scene_session="fixture-scene", reset_epoch=1,
        model_sha256=guard.model_semantic_sha256,
        qpos=tuple(float(x) for x in data.qpos),
        qvel=tuple(float(x) for x in data.qvel),
        neck_position=neck, neck_velocity=0., scene_received_wall_ns=10_000_000_000,
        scene_source_time_ns=1_000_000_000, feedback_source_ns=1_000_000_000,
        feedback_wall_ns=10_000_000_000, decision_sim_ns=1_000_000_000,
        decision_wall_ns=10_000_000_000)


def test_rest_to_rest_quintic_reports_continuous_internal_extrema():
    extrema = quintic_extrema(.1, 0., 0., .3, 0., 0., 1.2)
    assert extrema["position"][0] == pytest.approx(.1)
    assert extrema["position"][-1] == pytest.approx(.3)
    assert max(abs(value) for value in extrema["velocity"]) == pytest.approx(
        1.875 * .2 / 1.2)
    assert max(abs(value) for value in extrema["acceleration"]) == pytest.approx(
        5.773502691896258 * .2 / (1.2**2))
    assert any(0. < value < 1. for value in extrema["candidate_s"]["velocity"])
    assert any(0. < value < 1. for value in extrema["candidate_s"]["acceleration"])


def test_arbitrary_quintic_overshoot_is_seen_between_safe_endpoints():
    extrema = quintic_extrema(0., 8., 0., 0., -8., 0., .1)
    assert extrema["position"][0] == 0.
    assert extrema["position"][1] == pytest.approx(0., abs=1e-14)
    assert max(extrema["position"]) > 0.
    assert max(abs(value) for value in extrema["velocity"]) > 8.


def test_full_model_collision_is_found_inside_clear_endpoint_curve(guard):
    # A retained free bottle pose creates one interior head_mount collision in
    # the actual geometry-bound full model. Endpoints remain clear at 1 mm.
    theta = .7330382858376184
    distance = .0473
    center = (-.06, .06, .5791703831546664)
    bottle = (center[0] + distance*math.cos(theta),
              center[1] + distance*math.sin(theta), center[2])
    state = snapshot_for(guard, neck=0., bottle_pose=bottle)
    guard._check_collision_pose(state.qpos, 0.)
    guard._check_collision_pose(state.qpos, .5)
    with pytest.raises(PermissionError, match="HEAD_TRAJECTORY_PROTECTED_CONTACT"):
        guard._check_collision_pose(state.qpos, .25)
    with pytest.raises(PermissionError, match="HEAD_TRAJECTORY_PROTECTED_CONTACT"):
        guard._check_physical_path(state, .5, guard._duration_ns(.5))


def test_same_neck_curve_changes_result_when_full_free_body_pose_changes(guard):
    clear = snapshot_for(guard, neck=0.)
    result = guard._check_physical_path(clear, .5, guard._duration_ns(.5))
    assert result["safe"] is True
    theta = .7330382858376184
    distance = .0473
    center = (-.06, .06, .5791703831546664)
    bottle = (center[0] + distance*math.cos(theta),
              center[1] + distance*math.sin(theta), center[2])
    changed = snapshot_for(guard, neck=0., bottle_pose=bottle)
    assert changed.qpos[:7] == clear.qpos[:7]
    assert changed.qpos[21:28] != clear.qpos[21:28]
    with pytest.raises(PermissionError, match="HEAD_TRAJECTORY_PROTECTED_CONTACT"):
        guard._check_physical_path(changed, .5, guard._duration_ns(.5))


def test_scene_xml_hash_and_pristine_semantic_hash_are_distinct(guard):
    assert guard.model_xml_sha256 == MODEL_XML_SHA256
    assert guard.model_semantic_sha256 == MODEL_SEMANTIC_SHA256
    assert guard.model_xml_sha256 != guard.model_semantic_sha256
    # The checker preserves the pristine hash even though its private collision
    # model has the approved 1 mm margin inflation.
    assert model_sha256(guard.checker.model) != guard.checker.model_sha256


def test_full_model_sample_budget_refuses_before_replay(guard):
    state = snapshot_for(guard, neck=0.)
    with pytest.raises(PermissionError, match="HEAD_TRAJECTORY_SAMPLE_BUDGET"):
        guard._check_physical_path(state, .05, 101_000_000_000)


def test_approved_initial_arm_cup_full_state_and_geometry_prefix_are_replayed(
        guard, record_property):
    state = snapshot_for(guard, neck=.1)
    cup_joint = mujoco.mj_name2id(guard._model, mujoco.mjtObj.mjOBJ_JOINT,
                                  "cup_free_joint")
    bottle_joint = mujoco.mj_name2id(guard._model, mujoco.mjtObj.mjOBJ_JOINT,
                                     "bottle_free_joint")
    assert cup_joint >= 0 and guard._model.jnt_type[cup_joint] == mujoco.mjtJoint.mjJNT_FREE
    assert mujoco.mj_id2name(
        guard._model, mujoco.mjtObj.mjOBJ_BODY,
        int(guard._model.jnt_bodyid[cup_joint])) == "plastic_cup"
    cup_address = int(guard._model.jnt_qposadr[cup_joint])
    bottle_address = int(guard._model.jnt_qposadr[bottle_joint])
    assert cup_address == 7 and bottle_address == 21
    assert state.qpos[cup_address:cup_address + 7] == pytest.approx(
        (.02, -.28, .165, 1., 0., 0., 0.))
    assert state.qpos[bottle_address:bottle_address + 7] == pytest.approx(
        (.11, -.22, .19, 1., 0., 0., 0.))

    replayed = []
    check_pose = guard._check_collision_pose
    def record_real_replay(qpos, neck_position):
        replayed.append((tuple(qpos), float(neck_position)))
        return check_pose(qpos, neck_position)
    guard._check_collision_pose = record_real_replay
    guard._check_collision_pose(state.qpos, .1)
    proof = guard._check_physical_path(
        state, -.17559216195018026,
        guard._duration_ns(-.17559216195018026 - .1))
    assert proof["safe"] is True
    assert proof["prefix_envelope_rad"][0] >= guard.safe_interval[0]
    assert proof["prefix_envelope_rad"][1] <= guard.safe_interval[1]
    assert proof["prefix_sample_spacing_rad"] <= .001
    prefix_count = proof["prefix_envelope_samples"]
    assert len(replayed) == 1 + prefix_count + proof["main_samples"]
    prefix_positions = [position for _, position in replayed[1:1 + prefix_count]]
    main_positions = [position for _, position in replayed[1 + prefix_count:]]
    assert prefix_positions[0] == pytest.approx(proof["prefix_envelope_rad"][0])
    assert prefix_positions[-1] == pytest.approx(proof["prefix_envelope_rad"][1])
    assert max(abs(b - a) for a, b in zip(prefix_positions, prefix_positions[1:])) <= .001
    assert max(abs(b - a) for a, b in zip(main_positions, main_positions[1:])) <= .001
    assert all(qpos == pytest.approx(state.qpos) for qpos, _ in replayed)
    record_property("initial_full_qpos", list(state.qpos))
    record_property("initial_full_qvel", list(state.qvel))
    record_property("initial_cup_joint_mapping", {
        "joint": "cup_free_joint", "body": "plastic_cup",
        "qpos_address": cup_address,
        "xyz_quaternion": list(state.qpos[cup_address:cup_address + 7]),
    })
    record_property("initial_neck_to_coarse_edge_path", proof)


def test_guard_binds_exact_approved_base_protected_mask(guard):
    wrong_root = MujocoNeckSweepChecker(MODEL,
        expected_model_sha256=guard.model_semantic_sha256,
        protected_roots=("plastic_cup",), allowed_pairs=(),
        path_step_s=.002, path_clearance_m=.001, max_samples=50000)
    with pytest.raises(ValueError, match="HEAD_TRAJECTORY_PROTECTED_MASK_INVALID"):
        HeadTrajectoryGuard(checker=wrong_root,
            feedback_port=SimpleNamespace(feedback_snapshot=lambda: None),
            scene_observer=_Scene(guard.model_semantic_sha256),
            node=SimpleNamespace(get_clock=lambda: SimpleNamespace(
                now=lambda: SimpleNamespace(nanoseconds=1_000_000_000))),
            model_xml_path=MODEL, geometry_path=GEOMETRY,
            geometry_sha256=GEOMETRY_SHA256,
            simulation_session_id="fixture-scene", reset_epoch=1)


def _rich_goal_for_curve_validation():
    goal = FollowJointTrajectory.Goal()
    goal.trajectory.joint_names = ["neck_yaw_joint"]
    first = JointTrajectoryPoint()
    first.positions, first.velocities, first.accelerations = [.2], [0.], [0.]
    first.time_from_start.sec, first.time_from_start.nanosec = 0, 600_000_000
    last = JointTrajectoryPoint()
    last.positions, last.velocities, last.accelerations = [.3], [0.], [0.]
    last.time_from_start.sec, last.time_from_start.nanosec = 1, 800_000_000
    goal.trajectory.points = [first, last]
    return goal


@pytest.mark.parametrize("field,value", [
    ("velocities", [.01]), ("accelerations", [.01]), ("positions", [.2, .3]),
])
def test_actual_rich_ros_curve_guard_refuses_unsupported_derivative_shapes(
        guard, field, value):
    goal = _rich_goal_for_curve_validation()
    setattr(goal.trajectory.points[0], field, value)
    with pytest.raises(PermissionError):
        guard._validate_goal_curve(goal)


def test_actual_rich_ros_curve_guard_refuses_effort_payload(guard):
    goal = _rich_goal_for_curve_validation()
    goal.trajectory.points[0].effort = [.01]
    with pytest.raises(PermissionError, match="HEAD_TRAJECTORY_TYPED_DERIVATIVES_REQUIRED"):
        guard._validate_goal_curve(goal)


def test_actual_guard_accepts_acceleration_one_rest_to_rest_profile(guard):
    goal = _rich_goal_for_curve_validation()
    goal.trajectory.points[-1].positions = [.34]
    guard._validate_goal_curve(goal)


def test_actual_guard_accepts_acceleration_two_rest_to_rest_profile(guard):
    goal = _rich_goal_for_curve_validation()
    goal.trajectory.points[-1].positions = [.44]
    goal.trajectory.points[-1].time_from_start.nanosec = 600_000_000
    guard._validate_goal_curve(goal)


def test_actual_guard_accepts_velocity_one_acceleration_two_profile(guard):
    goal = _rich_goal_for_curve_validation()
    goal.trajectory.points[-1].positions = [.6]
    goal.trajectory.points[-1].time_from_start.nanosec = 700_000_000
    guard._validate_goal_curve(goal)


def test_collision_screen_keeps_one_milliradian_checked_pose_spacing(guard, monkeypatch):
    checked = []
    original = guard._check_collision_pose

    def check_pose(qpos, position):
        original(qpos, position)
        checked.append(position)

    monkeypatch.setattr(guard, '_check_collision_pose', check_pose)
    state = snapshot_for(guard, neck=0.)
    proof = guard._check_physical_path(state, .5, guard._duration_ns(.5))
    split = proof['prefix_envelope_samples']
    for positions in (checked[:split], checked[split:]):
        assert len(positions) >= 2
        assert max(abs(b - a) for a, b in zip(positions, positions[1:])) <= .001 + 1e-12
    assert proof['path_step_s'] == .002
    assert proof['clearance_m'] == .001


def test_actual_guard_rejects_continuous_velocity_over_limit_with_rest_derivatives(guard):
    goal = _rich_goal_for_curve_validation()
    goal.trajectory.points[-1].positions = [2.4]
    goal.trajectory.points[-1].time_from_start.sec = 4
    goal.trajectory.points[-1].time_from_start.nanosec = 600_000_000
    with pytest.raises(PermissionError, match="HEAD_TRAJECTORY_CONTINUOUS_LIMIT"):
        guard._validate_goal_curve(goal)


def test_actual_guard_rejects_continuous_acceleration_over_limit_with_rest_derivatives(guard):
    goal = _rich_goal_for_curve_validation()
    goal.trajectory.points[-1].time_from_start.sec = 1
    goal.trajectory.points[-1].time_from_start.nanosec = 100_000_000
    with pytest.raises(PermissionError, match="HEAD_TRAJECTORY_CONTINUOUS_LIMIT"):
        guard._validate_goal_curve(goal)


def test_actual_guard_rejects_rich_goal_outside_geometry_position_bounds(guard):
    goal = _rich_goal_for_curve_validation()
    goal.trajectory.points[-1].positions = [6.3]
    with pytest.raises(PermissionError,
                       match="HEAD_TRAJECTORY_TYPED_TIMING_OR_BOUNDS_INVALID"):
        guard._validate_goal_curve(goal)


def test_collision_replay_refuses_protected_mask_mutated_after_guard_binding(guard):
    state = snapshot_for(guard, neck=0.)
    theta, distance = .7330382858376184, .0473
    center = (-.06, .06, .5791703831546664)
    bottle = (center[0] + distance*math.cos(theta),
              center[1] + distance*math.sin(theta), center[2])
    changed = snapshot_for(guard, neck=0., bottle_pose=bottle)
    guard.checker.protected = frozenset()
    with pytest.raises(PermissionError, match="HEAD_TRAJECTORY_COLLISION_POLICY_MUTATED"):
        guard._check_collision_pose(changed.qpos, .25)


def test_collision_replay_refuses_clearance_margin_mutated_after_guard_binding(guard):
    state = snapshot_for(guard, neck=0.)
    guard.checker.model.geom_margin[:] = 0.
    with pytest.raises(PermissionError, match="HEAD_TRAJECTORY_COLLISION_POLICY_MUTATED"):
        guard._check_collision_pose(state.qpos, .1)
