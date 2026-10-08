"""B4b: the first-episode production composition selects the ACT station from the frozen inputs, not from ambient state.

The L1 run b4a1 launched the ORIGINAL pick-place profile (no neck controller) because the broker-era
`FirstEpisodeStation` had been deleted without a replacement and `ParallelWorkerRuntime` fell back to the default station.
"""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from launch import LaunchContext
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.utilities import perform_substitutions
from launch_ros.actions import Node

from so101_demo.parallel_batch.contracts import RunMode
from so101_demo.runtime import launch_composition as launch
from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime
from test_act_child_recorder_binding import frozen_child_inputs
from test_parallel_worker_runtime import _ProcessGroup, _resources

PACKAGE = Path(__file__).resolve().parents[1]
FORBIDDEN = ("act_command_" + "broker", "controller_" + "reservation")


def production_station(tmp_path):
    """The command and environment the production Worker composition produces for the frozen first-episode inputs."""
    manifest, document, snapshot = frozen_child_inputs(tmp_path)
    scope = tmp_path / "scope.json"
    resources = _resources(tmp_path / "w", "worker-01", 0, 181)
    processes = _ProcessGroup()
    runtime = build_worker_runtime(
        resources, RunMode.EXECUTE, process_group=processes,
        episode_inputs_manifest=str(manifest), episode_scope_path=str(scope),
        reset_point=lambda _lease: None, initial_gate=lambda *_a: object(), capture_rgb=lambda *_a: None)
    runtime.start_physical_runtime()
    assert len(processes.specs) == 1
    return processes.specs[0].argv, processes.environments[0], manifest, document, snapshot, runtime


def arguments(argv):
    return dict(item.split(":=", 1) for item in argv if ":=" in item)


def evaluated_nodes(argv):
    """Evaluate the launch file the production command names, with exactly the arguments it passes."""
    name = next(item for item in argv if item.endswith(".launch.py"))
    spec = importlib.util.spec_from_file_location("production_launch", PACKAGE / "launch" / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    description = module.generate_launch_description()
    context = LaunchContext()
    for action in description.entities:
        if isinstance(action, DeclareLaunchArgument) and action.default_value is not None:
            context.launch_configurations[action.name] = perform_substitutions(context, action.default_value)
    context.launch_configurations.update(arguments(argv))
    opaque = next(action for action in description.entities if isinstance(action, OpaqueFunction))
    found = []

    def walk(items):
        for item in items:
            if isinstance(item, Node):
                found.append((item, context))
            walk(getattr(item, "entities", None) or [])
    walk(opaque.execute(context))
    return found


@pytest.fixture(autouse=True)
def source_share(monkeypatch):
    # the launch reads config/ and assets/ from the package share; the source tree is the same layout
    monkeypatch.setattr(launch, "get_package_share_directory",
                        lambda name: str(PACKAGE) if name == "so101_demo_py" else "/opt/ros/jazzy/share/" + name)
    monkeypatch.setattr(os, "environ", os.environ.copy())


def test_the_production_station_is_the_act_launch_bound_to_the_frozen_inputs(tmp_path):
    argv, environment, manifest, document, snapshot, _ = production_station(tmp_path)
    assert "so101_mujoco_act.launch.py" in argv and "so101_mujoco_task_station.launch.py" not in argv
    values = arguments(argv)
    assert values["act_first_episode_inputs"] == str(manifest)
    assert values["act_expected_inputs_sha256"] == document["inputs_sha256"]
    assert values["mujoco_scene"].endswith(snapshot["scene_path"]) and "/execution/" in values["mujoco_scene"]
    assert values["headless"] == "true" and values["sensor_rendering"] == "true" and values["include_teleop"] == "false"
    # the ACT profile is explicit in the worker's own environment, not borrowed from the parent's
    assert environment["SO101_ACT_PROFILE"] == "1" and environment["SO101_SIMULATION_SESSION_ID"] == "session-worker-01"
    assert not any(any(token in item for token in FORBIDDEN) for item in list(argv) + list(environment))


def test_the_launch_the_production_command_evaluates_to_uses_the_act_profile_with_a_neck_and_no_broker(tmp_path):
    argv, *_ = production_station(tmp_path)
    nodes = evaluated_nodes(argv)
    executables = [(node.node_package, node.node_executable) for node, _ in nodes]
    assert ("mujoco_ros2_control", "ros2_control_node") in executables
    spawned = [node._Node__arguments[0] for node, _ in nodes if node.node_executable == "spawner"]
    assert spawned == ["joint_state_broadcaster", "arm_controller", "gripper_controller", "neck_controller"]
    simulator, context = next((node, c) for node, c in nodes if node.node_executable == "ros2_control_node")
    files = [perform_substitutions(context, item.param_file) for item in simulator._Node__parameters
             if hasattr(item, "param_file")]
    assert files == [str(PACKAGE / "config/mujoco/act/ros2_controllers.yaml"),
                     str(PACKAGE / "config/mujoco/act/mujoco_plugins.yaml")]
    assert all(str(PACKAGE / "config/mujoco/act") in node._Node__arguments[-1]
               for node, _ in nodes if node.node_executable == "spawner")
    assert not any(any(token in str(value) for token in FORBIDDEN)
                   for node, _ in nodes for value in [node.node_executable, node.node_package,
                                                      node._Node__arguments or ""])


def test_the_readiness_node_set_and_the_ready_probe_include_the_neck_for_the_act_profile(monkeypatch):
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts as Ports
    base = tuple(sorted(Ports.expected_worker_nodes() + (
        "/controller_manager", "/move_group/moveit", "/moveit_simple_controller_manager", "/robotsystem",
        "/move_group_private_1", "/moveit_1", "/transform_listener_impl_a")))
    assert Ports.worker_node_inventory_matches(tuple(sorted(base + ("/neck_controller",))), teacher_profile=True)
    assert not Ports.worker_node_inventory_matches(base, teacher_profile=True)       # the L1 failure: no neck
    seen = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: seen.append(argv) or SimpleNamespace(returncode=0, stdout="", stderr=""))
    ports = object.__new__(Ports)
    ports.dependencies = {"act_profile": True}
    assert ports.ready_probe(()) is True and "--include-neck" in seen[0]


def test_a_failed_ready_probe_leaves_its_reason_in_the_worker_result_not_only_in_a_log(tmp_path, monkeypatch):
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts as Ports
    reason = '{"failure_code": "MOTION_STACK_CONTROLLER_NOT_ACTIVE", "phase": "CONTROLLERS", "ready": false}'
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: SimpleNamespace(returncode=1, stdout=reason + "\n", stderr=""))
    ports = object.__new__(Ports)
    ports.dependencies = {"act_profile": True}
    assert ports.ready_probe(()) is False
    assert "MOTION_STACK_CONTROLLER_NOT_ACTIVE" in ports.ready_failure_message
    argv, environment, manifest, document, snapshot, runtime = production_station(tmp_path)
    runtime._ready_probe = ports.ready_probe
    assert runtime.worker_ready_gate() is False
    assert "MOTION_STACK_CONTROLLER_NOT_ACTIVE" in runtime.ready_failure()
