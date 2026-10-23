"""A side+wrist stack composes no head and no neck anywhere; a head+wrist stack composes exactly what it always did.

The composition of one ACT stack is read from every place that decides what exists in it: the launch actions (nodes, controller
spawners, the robot description, the scene, the camera plugin and controller files), the stack launch and readiness commands of
an instance, the node and controller inventory, the recorder topic list (the bag channels), the readiness checks, the controller
stop lanes, the controller reference streams, the synchronizer streams, the audit joints and the source keys. For the side+wrist rig
nothing of any of them may mention a head or a neck; for the head+wrist rig each is pinned to what it was before rigs existed.
"""

import hashlib
import os
from pathlib import Path
import re
import sys

import pytest
import yaml
from launch import LaunchContext
from launch.actions import DeclareLaunchArgument, OpaqueFunction, SetEnvironmentVariable
from launch.utilities import perform_substitutions
from launch_ros.actions import Node
from launch_ros.utilities import evaluate_parameters
from paths import PACKAGE_ROOT

from so101_demo.act.offline import raw_recorder, scan
from so101_demo.act.offline.engine import required_sources_for
from so101_demo.act.rig_files import rig_model_files
from so101_demo.act.rig_profile import HEAD_WRIST_RIG, KNOWN_RIGS, KNOWN_SOURCE_KEYS, SIDE_WRIST_RIG, source_keys_for
from so101_demo.act.synchronizer import RgbObservationSynchronizer
from so101_demo.act.teacher_collection import validate_reference_continuity
from so101_demo.adapters.act.controller_reference_observer import ControllerReferenceObserver
from so101_demo.cli import act_stack_ready
from so101_demo.runtime.act_instance.program import instance_stack_launch
from so101_demo.runtime.container_campaign import controller_stop
from so101_demo.runtime.launch_composition import task_station as launch_task_station
from so101_demo.runtime.parallel_ros_ports.binding import RuntimeBinding
from so101_teleop.unified.pick_place_startup_issuer import InstalledActStackReadinessProbe

#: head or neck in any spelling, except the simulator's `headless` parameter
_HEAD_OR_NECK = re.compile(r"neck|head(?!less)", re.IGNORECASE)


def _clean(*texts):
    return [match.group(0) for text in texts for match in _HEAD_OR_NECK.finditer(str(text))]


@pytest.fixture(autouse=True)
def isolated_launch_environment(monkeypatch):
    monkeypatch.setattr(os, "environ", os.environ.copy())


def _compose(tmp_path, monkeypatch, rig=None):
    """(nodes, context) of the headless ACT execution stack launch, composed from this checkout's files."""
    monkeypatch.setattr(launch_task_station, "get_package_share_directory", lambda package: str(PACKAGE_ROOT))
    description = launch_task_station.build_act_execution_stack_launch_description()
    context = LaunchContext()
    for action in description.entities:
        if isinstance(action, DeclareLaunchArgument) and action.default_value is not None:
            context.launch_configurations[action.name] = perform_substitutions(context, action.default_value)
    context.launch_configurations.update({"session_id": "act-composition-01", "task_evidence_root": str(tmp_path),
                                          **({} if rig is None else {"rig": rig})})
    opaque = next(action for action in description.entities if isinstance(action, OpaqueFunction))
    actions = opaque.execute(context)
    assert any(isinstance(action, SetEnvironmentVariable) for action in actions)
    return [action for action in actions if isinstance(action, Node)], context


def _simulator_parameters(nodes, context):
    simulator = next(node for node in nodes if node.node_executable == "ros2_control_node")
    return evaluate_parameters(context, simulator._Node__parameters)


def _files(parameters):
    return [Path(item) for item in parameters if isinstance(item, (str, Path))]


def _spawned(nodes):
    return [node._Node__arguments[0] for node in nodes if node.node_executable == "spawner"]


def test_head_wrist_launch_composition_is_what_it_was_before_rigs(tmp_path, monkeypatch):
    nodes, context = _compose(tmp_path, monkeypatch)
    assert [node.node_executable for node in nodes] == [
        "static_transform_publisher", "static_transform_publisher", "robot_state_publisher", "ros2_control_node",
        "spawner", "spawner", "spawner", "spawner", "graceful_shutdown_move_group", "scene_setup"]
    assert _spawned(nodes) == ["joint_state_broadcaster", "arm_controller", "gripper_controller", "neck_controller"]
    parameters = _simulator_parameters(nodes, context)
    assert [path.name for path in _files(parameters)] == ["ros2_controllers.yaml", "mujoco_plugins.yaml"]
    assert [path.parent for path in _files(parameters)] == [PACKAGE_ROOT / "config/mujoco/act"] * 2
    description = parameters[0]["robot_description"]
    expected = (PACKAGE_ROOT / "assets/mujoco/act/so101.urdf").read_text()
    for token, value in (("@SO101_MUJOCO_SCENE@", str(PACKAGE_ROOT / "assets/mujoco/act/scene.xml")),
                         ("@SO101_MUJOCO_INITIAL_KEYFRAME@", "task_start"), ("@SO101_MUJOCO_HEADLESS@", "true"),
                         ("@SO101_MUJOCO_DISABLE_RENDERING@", "false"), ("@SO101_MUJOCO_SIM_SPEED_FACTOR@", "1.0")):
        expected = expected.replace(token, value)
    assert description == expected and "neck_yaw_joint" in description and "head_camera_frame" in description
    assert context.launch_configurations["rig"] == "head-wrist"


def test_head_wrist_files_are_byte_identical_to_the_ones_the_sealed_data_ran_on():
    """The rig-v1 simulator files never changed: a head+wrist campaign binds exactly the bytes it always did."""
    pinned = {
        "assets/mujoco/act/scene.xml": "ea7e18df15dd67e8beddcc35d66eab6fda128145a7877b578fc641d282c114cb",
        "assets/mujoco/act/so101.xml": "264dd124c27d06a14a96baf2cc8bf7789c407a81a9ca648159957bf7713eebfe",
        "assets/mujoco/act/so101.urdf": "de48c1b97ed862b63b530d31daf7a7bdfb864aebe50370c5f7516f9520d78d9c",
        "config/mujoco/act/mujoco_plugins.yaml": "e24343b57fd54d767baaaa5992a12d01fa208b93f68105834be89b1d1b6fdc88",
        "config/mujoco/act/ros2_controllers.yaml": "b88d705d89a867f8c7cac375543f91eb04b08d1eb580a8e7c6f775f87a6388c5",
        "config/act/rig-v1.yaml": "1ac3dab6872983044854cdef788f3f054c9285e1c0ad8a7184b2fcd93f913af5",
    }
    files = rig_model_files(HEAD_WRIST_RIG)
    assert {files.scene, files.robot_mjcf, files.urdf, files.plugins, files.controllers, files.profile} == set(pinned)
    for relative, digest in pinned.items():
        assert hashlib.sha256((PACKAGE_ROOT / relative).read_bytes()).hexdigest() == digest, relative


def test_side_wrist_launch_composes_no_head_no_neck_and_the_side_wrist_files(tmp_path, monkeypatch):
    nodes, context = _compose(tmp_path, monkeypatch, rig="side-wrist")
    assert [node.node_executable for node in nodes] == [
        "static_transform_publisher", "static_transform_publisher", "robot_state_publisher", "ros2_control_node",
        "spawner", "spawner", "spawner", "graceful_shutdown_move_group", "scene_setup"]
    assert _spawned(nodes) == ["joint_state_broadcaster", "arm_controller", "gripper_controller"]
    parameters = _simulator_parameters(nodes, context)
    files = rig_model_files(SIDE_WRIST_RIG)
    assert _files(parameters) == [PACKAGE_ROOT / files.controllers, PACKAGE_ROOT / files.plugins]
    description = parameters[0]["robot_description"]
    assert str(PACKAGE_ROOT / files.scene) in description
    spawner_texts = [" ".join(map(str, node._Node__arguments)) for node in nodes if node.node_executable == "spawner"]
    plugin = yaml.safe_load(_files(parameters)[1].read_text())["/**"]["ros__parameters"]
    controllers = yaml.safe_load(_files(parameters)[0].read_text())
    assert _clean(description, *spawner_texts, yaml.safe_dump(plugin), yaml.safe_dump(controllers)) == []
    cameras = [key for key, value in plugin["mujoco_plugins"]["mujoco_camera_plugin"].items() if isinstance(value, dict)]
    assert sorted(cameras) == ["side_camera", "task_camera", "wrist_camera"]
    assert plugin["scalar_joint_audit_names"] == ["1", "2", "3", "4", "5", "6"]
    # the MoveIt node of the stack is given the same neckless description and the head-free SRDF
    move_group = next(node for node in nodes if node.node_executable == "graceful_shutdown_move_group")
    moveit = evaluate_parameters(context, move_group._Node__parameters)[0]
    assert _clean(moveit["robot_description"], moveit["robot_description_semantic"], yaml.safe_dump(moveit)) == []


def test_an_unknown_rig_or_a_rig_for_a_generic_station_is_refused(tmp_path, monkeypatch):
    with pytest.raises(RuntimeError, match="ACT_RIG_UNKNOWN"):
        _compose(tmp_path, monkeypatch, rig="top-wrist")


def _spec(name="act-composition-01"):
    return {"simulation_session_id": name}


def test_the_stack_launch_and_readiness_commands_name_the_rig_only_when_it_is_not_the_default(tmp_path):
    environment = {"PATH": "/usr/bin"}
    executable = tmp_path / "executable"
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o755)
    head = instance_stack_launch(_spec(), ros2=executable, stack_root=tmp_path, environment=environment)
    assert head.rig == "head-wrist" and head.rig_profile is None
    assert head.argv() == [str(executable), "launch", "so101_demo_py", "so101_mujoco_act_execution_stack.launch.py",
                           "headless:=true", "sensor_rendering:=true", "act_profile:=true",
                           "session_id:=act-composition-01", f"task_evidence_root:={tmp_path}"]
    assert head.readiness_arguments() == []
    side = instance_stack_launch(_spec(), ros2=executable, stack_root=tmp_path, environment=environment,
                                 rig=SIDE_WRIST_RIG, share=PACKAGE_ROOT)
    assert side.argv() == [*head.argv(), "rig:=side-wrist"]
    assert side.readiness_arguments() == ["--rig-profile", str(PACKAGE_ROOT / "config/act/rig-v2.yaml")]
    assert _clean(*side.argv(), *side.readiness_arguments()) == []

    def observer_argv(launch):
        seen = []

        def run(argv, **_kwargs):
            seen.append(argv)
            raise OSError("not run")

        with pytest.raises(ValueError, match="ACT_STACK_READINESS_COMMAND_FAILED"):
            InstalledActStackReadinessProbe(launch, executable, run=run)()
        return seen[0]

    assert observer_argv(head) == [str(executable), "--session-id", "act-composition-01", "--ros-domain-id",
                                   str(head.ros_domain_id), "--timeout-s", "60.0"]
    assert observer_argv(side) == [*observer_argv(head), "--rig-profile", str(PACKAGE_ROOT / "config/act/rig-v2.yaml")]


def test_a_non_default_rig_without_its_profile_file_is_not_a_launch(tmp_path):
    from so101_teleop.unified.act_stack import ActStackLaunch

    with pytest.raises(ValueError, match="ACT_STACK_RIG_INVALID"):
        ActStackLaunch(ros2_executable=Path(sys.executable), session_id="s", evidence_root=tmp_path, ros_domain_id=1,
                       environment={}, rig="side-wrist")
    with pytest.raises(ValueError, match="ACT_STACK_RIG_INVALID"):
        ActStackLaunch(ros2_executable=Path(sys.executable), session_id="s", evidence_root=tmp_path, ros_domain_id=1,
                       environment={}, rig_profile=PACKAGE_ROOT / "config/act/rig-v2.yaml")


_BASE_NODES = {"/arm_controller", "/gripper_controller", "/joint_state_broadcaster", "/move_group", "/mujoco_ros2_control_node",
               "/robot_state_publisher", "/so101_base_to_camera_link", "/so101_camera_link_to_task_camera_frame"}


def test_node_inventory_requires_the_neck_controller_only_for_a_rig_with_a_neck():
    for teacher_profile, rig, required in ((True, HEAD_WRIST_RIG, _BASE_NODES | {"/neck_controller"}),
                                           (True, None, _BASE_NODES | {"/neck_controller"}),
                                           (True, SIDE_WRIST_RIG, _BASE_NODES), (False, SIDE_WRIST_RIG, _BASE_NODES),
                                           (False, HEAD_WRIST_RIG, _BASE_NODES)):
        rules = RuntimeBinding.worker_node_inventory_rules(teacher_profile=teacher_profile, rig=rig)
        assert rules[0] == required
    nodes = tuple(sorted({*_BASE_NODES, "/controller_manager", "/move_group/moveit", "/moveit_simple_controller_manager",
                          "/robotsystem", "/move_group_private_1", "/moveit_1", "/transform_listener_impl_a"}))
    assert RuntimeBinding.worker_node_inventory_matches(nodes, teacher_profile=True, rig=SIDE_WRIST_RIG)
    assert not RuntimeBinding.worker_node_inventory_matches(nodes, teacher_profile=True, rig=HEAD_WRIST_RIG)
    assert not RuntimeBinding.worker_node_inventory_matches(nodes, teacher_profile=True)
    # a neck controller that a head-less stack should not have is an unknown node
    with_neck = tuple(sorted((*nodes, "/neck_controller")))
    assert not RuntimeBinding.worker_node_inventory_matches(with_neck, teacher_profile=True, rig=SIDE_WRIST_RIG)
    assert RuntimeBinding.worker_node_inventory_report(with_neck, teacher_profile=True, rig=SIDE_WRIST_RIG)["unknown"] == [
        "/neck_controller"]


def test_recorder_topics_bag_channels_and_scan_streams_have_no_head_or_neck_for_the_side_wrist_rig():
    side, head = SIDE_WRIST_RIG, HEAD_WRIST_RIG
    topics = raw_recorder.topics_for(side)
    assert topics == ("/clock", "/side_camera/color", "/side_camera/camera_info", "/wrist_camera/color",
                      "/wrist_camera/camera_info", *raw_recorder.SIMULATION_TOPICS, "/joint_states",
                      "/arm_controller/controller_state", "/gripper_controller/controller_state", raw_recorder.EVENTS_TOPIC,
                      raw_recorder.SCENE_READS_TOPIC)
    channels = (*topics, *raw_recorder.core_topics_for(side), *raw_recorder.deep_reliable_for(side),
                *scan.controller_state_topics_for(side), *required_sources_for(side))
    assert _clean(*channels) == []
    # the head+wrist rig is exactly the lists it always had
    assert raw_recorder.TOPICS == raw_recorder.topics_for(head) and "/neck_controller/controller_state" in raw_recorder.TOPICS
    assert raw_recorder.topics_for(head)[1:5] == ("/head_camera/color", "/head_camera/camera_info", "/wrist_camera/color",
                                                  "/wrist_camera/camera_info")
    assert raw_recorder.CORE_TOPICS == raw_recorder.core_topics_for(head)
    assert raw_recorder.DEEP_RELIABLE == raw_recorder.deep_reliable_for(head)
    assert scan.CONTROLLER_STATE_TOPICS == scan.controller_state_topics_for(head)


def test_readiness_checks_and_actions_have_no_head_or_neck_for_the_side_wrist_rig():
    side, head = SIDE_WRIST_RIG, HEAD_WRIST_RIG
    assert act_stack_ready.controllers_for(side) == ("joint_state_broadcaster", "arm_controller", "gripper_controller")
    assert act_stack_ready.actions_for(side) == ("/execute_trajectory", "/arm_controller/follow_joint_trajectory",
                                                 "/gripper_controller/follow_joint_trajectory")
    assert [name for name, _code in act_stack_ready.check_order_for(side)] == [
        "mujoco_session", "advancing_physics", "controller_states", "moveit_graph", "physical_stop", "side_rgb", "wrist_rgb"]
    assert _clean(*act_stack_ready.controllers_for(side), *act_stack_ready.actions_for(side),
                  *(item for pair in act_stack_ready.check_order_for(side) for item in pair)) == []
    assert act_stack_ready.controllers_for(head) == act_stack_ready._CONTROLLERS
    assert act_stack_ready.actions_for(head) == act_stack_ready._ACTIONS
    assert act_stack_ready.check_order_for(head) == act_stack_ready._CHECK_ORDER
    assert act_stack_ready._CONTROLLERS[-1] == "neck_controller" and "head_rgb" in dict(act_stack_ready._CHECK_ORDER)


def test_controller_stop_lanes_have_no_neck_lane_for_a_neckless_stack():
    assert set(controller_stop.lanes_for(True)) == {"arm", "gripper", "neck", "moveit"}
    assert set(controller_stop.lanes_for(False)) == {"arm", "gripper", "moveit"}
    assert _clean(*controller_stop.lanes_for(False).values()) == []


def _lane(prefix, statuses=()):
    return {"action_prefix": prefix, "cancel_sent_monotonic_ns": 10, "cancel_received_monotonic_ns": 11,
            "cancel_return_code": 0, "goals_canceling": [], "status_received_monotonic_ns": 12, "statuses": list(statuses)}


def _observation(lanes, **extra):
    document = {"schema_version": controller_stop.SCHEMA_VERSION, "kind": "ACT_CONTROLLER_STOP_OBSERVATION",
                "started_monotonic_ns": 1, "completed_monotonic_ns": 20, "lanes": lanes, **extra}
    return controller_stop.ControllerStopObservation(controller_stop.canonical_json(document))


def test_a_stop_observation_without_a_neck_lane_must_say_so_and_one_that_does_not_has_all_four_lanes():
    four = {name: _lane(prefix) for name, prefix in controller_stop.lanes_for(True).items()}
    three = {name: lane for name, lane in four.items() if name != "neck"}
    assert _observation(four).proven and _observation(three, without_neck=True).proven
    assert "without_neck" not in _observation(four).document
    for lanes, extra in ((three, {}), (four, {"without_neck": True}), (three, {"without_neck": False})):
        with pytest.raises(ValueError, match="ACT_CONTROLLER_STOP_OBSERVATION_INVALID"):
            _observation(lanes, **extra)


def test_controller_reference_continuity_has_no_neck_block_for_a_neckless_rig():
    observer = ControllerReferenceObserver(max_frames=100, kinds=("arm", "gripper"))
    observer.reset("s", 1, source_floor_ns=0)
    report = observer.gap_report()
    assert set(report["kinds"]) == {"arm", "gripper"}
    assert validate_reference_continuity(report) is report
    full = ControllerReferenceObserver(max_frames=100)
    full.reset("s", 1, source_floor_ns=0)
    assert set(full.gap_report()["kinds"]) == {"arm", "gripper", "neck"}
    assert validate_reference_continuity(full.gap_report())
    with pytest.raises(ValueError):
        ControllerReferenceObserver(max_frames=100, kinds=("arm", "head"))
    # a report of any other controller set is refused
    odd = dict(report, kinds={"gripper": report["kinds"]["gripper"], "neck": report["kinds"]["arm"]})
    with pytest.raises(ValueError):
        validate_reference_continuity(odd)


def test_synchronizer_streams_and_source_keys_have_no_head_or_neck_for_the_side_wrist_rig():
    side = RgbObservationSynchronizer(max_age_s=0.1, max_skew_s=0.1, rig=SIDE_WRIST_RIG)
    assert side.streams == ("side", "wrist", "arm") and set(side.buffers) == {"side", "wrist", "arm"}
    head = RgbObservationSynchronizer(max_age_s=0.1, max_skew_s=0.1)
    assert head.streams == ("head", "wrist", "arm", "neck") == RgbObservationSynchronizer.STREAMS
    assert source_keys_for(SIDE_WRIST_RIG) == ("world", "scene", "contact", "side", "wrist", "arm")
    assert source_keys_for(HEAD_WRIST_RIG) == ("world", "scene", "contact", "head", "wrist", "arm", "neck")
    assert _clean(*source_keys_for(SIDE_WRIST_RIG), *side.streams) == []
    assert KNOWN_SOURCE_KEYS == tuple(source_keys_for(rig) for rig in KNOWN_RIGS.values())
