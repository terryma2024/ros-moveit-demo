"""R3-a: `transactional_reset` and `execute_mujoco_reset` carry a start joint pose into `MujocoResetClient.reset(joint_overrides=...)`.

Without one, the reset is the all-zero reset it always was (the existing tests pin that call too)."""

import pytest

from so101_demo.act.joints import ACT_JOINTS, ARM_JOINTS
from so101_demo.act.rig_profile import HEAD_WRIST_RIG, SIDE_WRIST_RIG
from so101_demo.backends.mujoco import teleop_runtime

START6 = (0.12, -0.03, 0.08, -0.1, 0.02, 0.0)
START7 = (*START6, 0.0)


@pytest.fixture()
def harness(monkeypatch):
    built, resets = [], []

    class Node:
        def destroy_node(self):
            pass

    class Scope:
        def create_node(self, name):
            return Node()

        def client_options(self):
            return {}

        def close(self):
            pass

        def abandon(self, nodes=()):
            pass

    class Services:
        def __init__(self, *args, **kwargs):
            pass

        def latest_joint_positions(self):
            return (0.0,) * 6

    class Resetter:
        def __init__(self, *args, **kwargs):
            built.append(kwargs)

        def reset(self, keyframe, free_joint_overrides=(), **kwargs):
            resets.append(tuple((item.name, item.position, item.velocity) for item in kwargs["joint_overrides"]))
            return "receipt"

    monkeypatch.setattr(teleop_runtime, "_RosScope", Scope)
    monkeypatch.setattr(teleop_runtime, "MujocoRosClient", Services)
    monkeypatch.setattr(teleop_runtime, "MujocoWorldObserver", lambda *args, **kwargs: object())
    monkeypatch.setattr(teleop_runtime, "MujocoResetClient", Resetter)
    return built, resets


@pytest.mark.parametrize("rig,joints,start", [(SIDE_WRIST_RIG, ARM_JOINTS, START6), (HEAD_WRIST_RIG, ACT_JOINTS, START7)])
def test_a_start_pose_is_the_expected_feedback_and_the_override_of_every_act_joint(harness, rig, joints, start):
    built, resets = harness
    teleop_runtime.transactional_reset("s", act_profile=True, rig=rig, start_joint_positions=start)
    assert built[0]["expected_joint_positions"] == start and built[0]["expected_joint_names"] == joints
    assert resets == [tuple((name, position, 0.0) for name, position in zip(joints, start))]


@pytest.mark.parametrize("rig,joints", [(SIDE_WRIST_RIG, ARM_JOINTS), (HEAD_WRIST_RIG, ACT_JOINTS)])
def test_without_a_start_pose_the_reset_is_all_zero(harness, rig, joints):
    built, resets = harness
    teleop_runtime.transactional_reset("s", act_profile=True, rig=rig)
    assert built[0]["expected_joint_positions"] == (0.0,) * len(joints)
    assert resets == [tuple((name, 0.0, 0.0) for name in joints)]


@pytest.mark.parametrize("start", [(0.0,) * 5, (0.0,) * 8, (float("nan"),) + (0.0,) * 5, "abc"])
def test_a_start_pose_of_the_wrong_length_or_not_finite_is_refused_before_any_reset(harness, start):
    built, resets = harness
    with pytest.raises(ValueError, match="START_JOINT_POSITIONS"):
        teleop_runtime.transactional_reset("s", act_profile=True, rig=SIDE_WRIST_RIG, start_joint_positions=start)
    assert resets == []


def test_a_start_pose_needs_the_act_profile(harness):
    with pytest.raises(ValueError, match="START_JOINT_POSITIONS"):
        teleop_runtime.transactional_reset("s", start_joint_positions=START6)


def test_execute_mujoco_reset_passes_the_start_pose_only_when_given(monkeypatch):
    from types import SimpleNamespace

    from so101_demo.cli import teleop_reset

    seen = []
    monkeypatch.setattr(teleop_reset, "transactional_reset", lambda session, **kwargs: seen.append(kwargs) or "receipt")
    monkeypatch.setattr(teleop_reset, "execute_scene_operation", lambda *a: SimpleNamespace(success=True))
    teleop_reset.execute_mujoco_reset("s", keyframe="task_start", cup_position_world_m=(0.0, 0.0, 0.1), act_profile=True, rig=SIDE_WRIST_RIG)
    teleop_reset.execute_mujoco_reset("s", keyframe="task_start", cup_position_world_m=(0.0, 0.0, 0.1), act_profile=True, rig=SIDE_WRIST_RIG,
                                      start_joint_positions=START6)
    assert "start_joint_positions" not in seen[0] and seen[1]["start_joint_positions"] == START6
