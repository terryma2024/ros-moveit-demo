"""The ACT reset (neck controller, seven joints, scalar snapshot, neck readiness) works with no broker.

Decision 2: the ACT reset logic stays; only the broker, lease and reservation pieces are cut. `b1b-reset-cut.md`.
"""
import inspect
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest
from paths import PACKAGE_ROOT, TEST_IMPORT_PATH

BROKER_PARAMETERS = {"control_context", "broker_connection", "initial_empty_retirement", "operation_guard"}


def test_reset_entry_points_have_no_broker_parameters_and_the_act_profile_is_explicit():
    from so101_demo.backends.mujoco.client import MujocoRosClient
    from so101_demo.backends.mujoco.reset import MujocoResetClient
    from so101_demo.backends.mujoco.teleop_runtime import current_evidence, transactional_reset
    from so101_demo.cli.teleop_reset import execute_mujoco_reset
    for function in (MujocoRosClient.__init__, MujocoResetClient.__init__, current_evidence,
                     transactional_reset, execute_mujoco_reset):
        assert not BROKER_PARAMETERS & set(inspect.signature(function).parameters), function
    assert "act_profile" in inspect.signature(transactional_reset).parameters
    assert "act_profile" in inspect.signature(execute_mujoco_reset).parameters
    for name in ("prepare_reset", "finish_reset", "_control_connection"):
        assert not hasattr(MujocoRosClient, name), name


def test_seven_joint_act_reset_with_the_neck_controller_runs_with_no_broker_module_imported():
    script = f"import sys; sys.path[:0] = {[*map(str, TEST_IMPORT_PATH)]!r}; import act_reset_driver as d; print('B1BJSON ' + __import__('json').dumps(d.run()))"
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120, check=False)
    line = next((x for x in done.stdout.splitlines() if x.startswith("B1BJSON ")), None)
    assert line is not None, done.stdout[-1500:] + done.stderr[-2500:]
    result = json.loads(line[len("B1BJSON "):])
    assert result["new_epoch"] == 4 and result["audit"] is True and result["scalar"] is True
    assert result["broker"] == []
    assert result["names"] == ["1", "2", "3", "4", "5", "6", "neck_yaw_joint"]
    switches = [event for event in result["events"] if event[0] == "switch"]
    assert switches[0][2] == ["arm_controller", "gripper_controller", "neck_controller"]
    assert switches[1][1] == ["arm_controller", "gripper_controller", "neck_controller"]
    reset = next(event for event in result["events"] if event[0] == "reset_world")
    assert reset[2] == ["1", "2", "3", "4", "5", "6", "neck_yaw_joint"]


def test_six_joint_act_reset_of_a_rig_without_a_neck_switches_no_neck_controller_and_audits_six_joints():
    script = (f"import sys; sys.path[:0] = {[*map(str, TEST_IMPORT_PATH)]!r}; import act_reset_driver as d; "
              "print('B1BJSON ' + __import__('json').dumps(d.run(False)))")
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120, check=False)
    line = next((x for x in done.stdout.splitlines() if x.startswith("B1BJSON ")), None)
    assert line is not None, done.stdout[-1500:] + done.stderr[-2500:]
    result = json.loads(line[len("B1BJSON "):])
    assert result["new_epoch"] == 4 and result["audit"] is True and result["scalar"] is True and result["broker"] == []
    arm = ["1", "2", "3", "4", "5", "6"]
    assert result["audit_names"] == arm and result["names"] == arm
    switches = [event for event in result["events"] if event[0] == "switch"]
    assert switches[0][2] == ["arm_controller", "gripper_controller"] and switches[1][1] == ["arm_controller", "gripper_controller"]
    reset = next(event for event in result["events"] if event[0] == "reset_world")
    assert reset[2] == arm
    assert "neck" not in json.dumps(result)


def test_the_scalar_joint_audit_reads_the_joints_it_was_enabled_for():
    from types import SimpleNamespace
    from so101_mujoco_support.msg import ScalarJointEvidence
    from so101_demo.act.joints import ARM_JOINTS
    from so101_demo.backends.mujoco.client import MujocoRosClient

    class Node:
        def create_client(self, kind, topic):
            return topic

        def create_subscription(self, kind, topic, callback, qos):
            return topic

    def evidence(names):
        message = ScalarJointEvidence(joint_names=list(names), positions_rad=[0.0] * len(names),
                                      velocities_rad_s=[0.0] * len(names), simulation_session_id="s", reset_epoch=3,
                                      simulation_step=0, paused=True)
        message.header.stamp.sec = 10
        return message

    client = MujocoRosClient(Node(), Node())
    client.enable_reset_joint_audit(ARM_JOINTS)
    client._scalar_joint_callback(evidence((*ARM_JOINTS, "neck_yaw_joint")))
    assert client.scalar_joint_callback_count == 0     # a neck the rig does not have is not the audited set
    client._scalar_joint_callback(evidence(tuple(reversed(ARM_JOINTS))))
    assert client.scalar_joint_callback_count == 1
    assert client.reset_joint_snapshot(ARM_JOINTS)["positions"] == (0.0,) * 6


def test_the_reset_transaction_of_a_rig_without_a_neck_names_no_neck(monkeypatch):
    """transactional_reset builds its reset client from the rig: the neck controller and the neck joint only for a rig with a neck."""
    from so101_demo.act.joints import ACT_JOINTS, ARM_JOINTS
    from so101_demo.act.rig_profile import HEAD_WRIST_RIG, SIDE_WRIST_RIG
    from so101_demo.backends.mujoco import teleop_runtime

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
            resets.append(tuple(item.name for item in kwargs["joint_overrides"]))
            return "receipt"

    monkeypatch.setattr(teleop_runtime, "_RosScope", Scope)
    monkeypatch.setattr(teleop_runtime, "MujocoRosClient", Services)
    monkeypatch.setattr(teleop_runtime, "MujocoWorldObserver", lambda *args, **kwargs: object())
    monkeypatch.setattr(teleop_runtime, "MujocoResetClient", Resetter)
    for rig, joints, controllers in ((HEAD_WRIST_RIG, ACT_JOINTS, ("arm_controller", "gripper_controller", "neck_controller")),
                                     (SIDE_WRIST_RIG, ARM_JOINTS, ("arm_controller", "gripper_controller"))):
        built.clear()
        resets.clear()
        teleop_runtime.transactional_reset("s", act_profile=True, rig=rig)
        assert built[0]["controller_names"] == controllers
        assert built[0]["expected_joint_names"] == joints and built[0]["expected_joint_positions"] == (0.0,) * len(joints)
        assert built[0]["act_audit"] is True
        assert resets == [joints]


def test_mujoco_ros_client_plain_services_even_when_a_context_file_is_in_the_environment(monkeypatch):
    from so101_demo.backends.mujoco.client import MujocoRosClient
    made = []

    class Node:
        def create_client(self, _kind, topic):
            made.append(topic)
            return object()

        def create_subscription(self, *_args):
            return None

    monkeypatch.setenv("SO101_ACT_CONTROL_CONTEXT", "/nonexistent")
    MujocoRosClient(Node(), Node())
    assert "/mujoco_ros2_control_node/reset_world" in made and "/controller_manager/switch_controller" in made


def ports(**dependencies):
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts
    resources = SimpleNamespace(session_id="s", worker_id="w", generation=1)
    return ParallelRosRuntimePorts(resources, catalog={}, dependencies=dependencies)


def test_act_profile_requires_the_neck_controller_but_not_a_broker_node():
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts
    base = set(ParallelRosRuntimePorts.expected_worker_nodes()) | {
        "/controller_manager", "/move_group/moveit", "/moveit_simple_controller_manager", "/robotsystem",
        "/move_group_private_1", "/moveit_2", "/transform_listener_impl_ab"}
    with_neck = tuple(sorted(base | {"/neck_controller"}))
    with_broker = tuple(sorted(base | {"/neck_controller", "/act_command_broker"}))
    assert ParallelRosRuntimePorts.worker_node_inventory_matches(with_neck, teacher_profile=True) is True
    assert ParallelRosRuntimePorts.worker_node_inventory_matches(with_broker, teacher_profile=True) is False
    assert ParallelRosRuntimePorts.worker_node_inventory_matches(tuple(sorted(base)), teacher_profile=True) is False


def test_ready_probe_asks_for_the_neck_in_the_act_profile_and_waits_for_no_broker(monkeypatch):
    import subprocess

    seen = []
    monkeypatch.setattr(subprocess, "run", lambda command, **_kw: seen.append(list(command)) or SimpleNamespace(returncode=0, stdout="", stderr=""))
    assert ports(act_profile=True).ready_probe(None) is True
    assert "--include-neck" in seen[-1]
    assert ports().ready_probe(None) is True
    assert "--include-neck" not in seen[-1]


def test_pause_and_resume_use_the_retained_pause_control_in_the_act_profile():
    calls = []
    control = SimpleNamespace(set_paused=lambda value: calls.append(value) or True, close=lambda: None)
    value = ports(act_profile=True, pause_control_factory=lambda: control)
    receipt = SimpleNamespace(simulation_session_id="s", reset_epoch_value=4)
    assert value.pause_physics(None, receipt) is True and value.resume_physics(None, receipt) is True
    assert calls == [True, False]


def test_worker_kwargs_carry_no_lifecycle_acknowledgements():
    keys = set(ports(act_profile=True).kwargs())
    assert not keys & {"initializing_acknowledged", "heartbeat_acknowledged", "attempt_started_acknowledged",
                       "finalizing_acknowledged", "execute_consumer_context"}


def test_no_teacher_lifecycle_in_the_reset_path_sources():
    root = PACKAGE_ROOT / "src"
    relatives = ["backends/mujoco/reset.py", "backends/mujoco/client.py", "backends/mujoco/teleop_runtime.py",
                 "cli/teleop_reset.py", "runtime/parallel_ros_runtime.py", "cli/mujoco_parallel_batch.py"]
    # the ports and the batch command live in these packages now
    for package in ("runtime/parallel_ros_ports", "cli/mujoco_batch"):
        relatives += sorted(path.relative_to(root).as_posix() for path in (root / package).glob("*.py"))
    for relative in relatives:
        text = (root / relative).read_text()
        for forbidden in ("leased_action_client", "teacher_worker_lifecycle", "TeacherWorkerLifecycle",
                          "initial_empty_retirement", "broker_connection", "act_command_broker"):
            assert forbidden not in text, (relative, forbidden)
