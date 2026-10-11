"""The unified child must be the only ACT command broker in its ROS domain."""

import importlib.util
import os

import pytest
from launch import LaunchContext
from launch.actions import DeclareLaunchArgument, OpaqueFunction, SetEnvironmentVariable
from launch.utilities import perform_substitutions
from launch_ros.actions import Node
from launch_ros.utilities import evaluate_parameters

from so101_demo.runtime.launch_composition import mujoco_actions as launch_mujoco_actions
from so101_demo.runtime.launch_composition import perception as launch_perception
from so101_demo.runtime.launch_composition import task_station as launch_task_station
from so101_demo.runtime.launch_composition import text_pick_agent as launch_text_pick_agent
from paths import PACKAGE_ROOT


@pytest.fixture(autouse=True)
def isolated_launch_environment(monkeypatch):
    """LaunchContext.environment writes must stay inside this test case."""
    monkeypatch.setattr(os, "environ", os.environ.copy())


def configured(tmp_path, *, overrides=None):
    description = launch_task_station.build_act_execution_stack_launch_description()
    context = LaunchContext()
    for action in description.entities:
        if isinstance(action, DeclareLaunchArgument) and action.default_value is not None:
            context.launch_configurations[action.name] = perform_substitutions(
                context, action.default_value)
    context.launch_configurations.update({
        "session_id": "act-pick-place-case-01", "task_evidence_root": str(tmp_path),
        **(overrides or {}),
    })
    opaque = next(action for action in description.entities if isinstance(action, OpaqueFunction))
    return description, context, opaque


@pytest.mark.parametrize("overrides,reason", [
    ({"headless": "false"}, "ACT_STACK_HEADLESS_REQUIRED"),
    ({"sensor_rendering": "false"}, "ACT_STACK_RGB_REQUIRED"),
    ({"act_profile": "false"}, "ACT_STACK_PROFILE_REQUIRED"),
    ({"session_id": "bad session"}, "ACT_STACK_SESSION_INVALID"),
    ({"task_evidence_root": "relative"}, "ACT_STACK_ROOT_INVALID"),
])
def test_invalid_act_stack_request_refuses_before_graph_construction(tmp_path, monkeypatch, overrides, reason):
    _, context, opaque = configured(tmp_path, overrides=overrides)
    made = []
    monkeypatch.setattr(launch_perception, "_mujoco_stack_actions", lambda *args, **kwargs: made.append(True))
    monkeypatch.setattr(launch_task_station, "_mujoco_stack_actions", lambda *args, **kwargs: made.append(True))
    monkeypatch.setattr(launch_text_pick_agent, "_mujoco_stack_actions", lambda *args, **kwargs: made.append(True))
    monkeypatch.setattr(launch_mujoco_actions, "_mujoco_stack_actions", lambda *args, **kwargs: made.append(True))
    with pytest.raises(RuntimeError, match=reason):
        opaque.execute(context)
    assert made == []


def test_public_act_execution_stack_launch_is_thin():
    path = PACKAGE_ROOT / "launch/so101_mujoco_act_execution_stack.launch.py"
    spec = importlib.util.spec_from_file_location("act_execution_stack_launch", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.generate_launch_description() is not None
