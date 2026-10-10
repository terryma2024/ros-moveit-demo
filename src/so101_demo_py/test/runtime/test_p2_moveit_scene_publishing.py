"""Pilot 8d9ed9d3: the planning-scene reads lost the colour of the attached cup about 250 ms after the attach, in both pilot bags.

Reproduced with MoveIt's own PlanningSceneMonitor on the Teacher's recorded apply requests
(`so101_mujoco_support`, test_planning_scene_colour_after_acm_apply): a monitor that publishes `/monitored_planning_scene`
keeps its scene as a diff of a parent scene, and the publishing thread's push and clear of that diff drops the colour of an
attached object. A monitor that does not publish keeps it. Nothing in the ACT stack reads `/monitored_planning_scene`
(only RViz does), so the ACT profile's move_group does not publish."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchContext
from launch_ros.utilities import evaluate_parameters

from so101_demo.runtime import launch_composition
from so101_demo.runtime.launch_composition import MUJOCO_CUP_KEYFRAMES

# the installed data (assets, config) the launch code itself reads, not a path relative to the sources
PACKAGE_ROOT = Path(get_package_share_directory("so101_demo_py"))
FLAGS = ("publish_planning_scene", "publish_geometry_updates", "publish_state_updates", "publish_transforms_updates")


def _move_group_parameters(act_profile: bool) -> dict:
    context = LaunchContext()
    context.launch_configurations.update(
        mujoco_scene=str(PACKAGE_ROOT / ("assets/mujoco/act/scene.xml" if act_profile else "assets/mujoco/scene.xml")),
        mujoco_initial_keyframe=MUJOCO_CUP_KEYFRAMES[0], headless="true", sensor_rendering="true", readiness_timeout_s="90.0",
        act_profile="true" if act_profile else "false")
    stack = launch_composition._mujoco_stack_actions(context, PACKAGE_ROOT, "publishing-session")
    return evaluate_parameters(context, stack.move_group._Node__parameters)[0]


def test_the_act_profile_move_group_does_not_publish_the_monitored_scene():
    parameters = _move_group_parameters(True)
    assert [parameters[flag] for flag in FLAGS] == [False, False, False, False]


def test_the_other_stacks_keep_publishing_for_rviz():
    parameters = _move_group_parameters(False)
    assert [parameters[flag] for flag in FLAGS] == [True, True, True, True]


def test_moveit_parameters_take_the_publishing_switch():
    on = launch_composition._moveit_parameters(PACKAGE_ROOT, "<robot/>")
    off = launch_composition._moveit_parameters(PACKAGE_ROOT, "<robot/>", publish_planning_scene=False)
    assert all(on[flag] is True for flag in FLAGS) and all(off[flag] is False for flag in FLAGS)
    assert {key: value for key, value in on.items() if key not in FLAGS} == {
        key: value for key, value in off.items() if key not in FLAGS}
