"""An admitted Task 8 stack uses fresh bounded stop and graph probes."""

from pathlib import Path
import json
import subprocess
import time
from types import SimpleNamespace
import uuid

import pytest

from so101_teleop.unified.act_stack import ActStackProcessOwner
from so101_teleop.unified.bridge import ActChildLaunch
from so101_teleop.unified.task8_startup_issuer import InstalledActStackReadinessProbe
from so101_teleop.unified.act_stack_probes import (
    RepeatableActStackStopProbe, RosGraphClearProbe, make_pick_place_act_stack,
)


def executable(tmp_path, name):
    binary = tmp_path / name
    binary.write_text("#!/usr/bin/env python3\n")
    binary.chmod(0o700)
    return binary


def scope(tmp_path):
    context = SimpleNamespace(
        campaign_id="campaign-290", workload_kind="task8_full", worker_count=1,
        execution_generation=3, evidence_root=str(tmp_path),
    )
    child = ActChildLaunch(
        campaign_id="campaign-290", worker_id="w1", execution_generation=3,
        ros_domain_id=176, namespace="/act/w1", controller_name="arm_controller_w1",
        mujoco_session_id="session-290",
        socket_root=f"/tmp/a290-{uuid.uuid4().hex[:8]}",
    )
    return context, child


def test_factory_binds_distinct_start_and_stop_observers_to_one_domain(tmp_path):
    context, child = scope(tmp_path)
    ros2 = executable(tmp_path, "ros2")
    observer = executable(tmp_path, "act_stack_ready")
    stack = make_pick_place_act_stack(
        context, child, ros2_executable=ros2, readiness_executable=observer,
        base_environment={"AMENT_PREFIX_PATH": "/task/overlay"},
    )
    assert isinstance(stack, ActStackProcessOwner)
    assert isinstance(stack.ready_probe, InstalledActStackReadinessProbe)
    assert isinstance(stack.stop_probe, RepeatableActStackStopProbe)
    assert stack.ready_probe is not stack.stop_probe
    assert stack.launch.evidence_root == tmp_path / "task8-live" / "campaign-290" / "stack"
    assert stack.launch.process_environment()["ROS_DOMAIN_ID"] == "176"
    assert stack.launch.process_environment()["GZ_PARTITION"] == "act-task8-176-campaign-290"
    assert stack.stop_probe.timeout_s < stack.stop_timeout_s
    assert stack.graph_clear_probe.launch is stack.launch


def test_stop_probe_reobserves_a_still_live_stack_on_retry(tmp_path):
    from so101_teleop.unified.act_stack import ActStackLaunch

    ros2 = executable(tmp_path, "ros2")
    observer = executable(tmp_path, "act_stack_ready")
    launch = ActStackLaunch(
        ros2_executable=ros2, session_id="session-290", evidence_root=tmp_path,
        ros_domain_id=176, environment={"GZ_PARTITION": "act-task8-176-campaign-290"},
    )
    calls = []
    artifact = {
        "schema_version": 1, "session_id": launch.session_id,
        "ros_domain_id": launch.ros_domain_id,
        "captured_monotonic_ns": time.monotonic_ns(),
        "checks": {key: True for key in (
            "mujoco_session", "advancing_physics", "controller_states",
            "moveit_graph", "physical_stop", "head_rgb", "wrist_rgb",
        )},
    }

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, json.dumps(artifact).encode(), b"")

    probe = RepeatableActStackStopProbe(launch, observer, run=runner)
    assert probe() is True
    assert probe() is True
    assert len(calls) == 2
    assert all(call[1]["timeout"] < 15.0 for call in calls)


def test_factory_rejects_wrong_generation_before_creating_stack_scope(tmp_path):
    context, child = scope(tmp_path)
    child = ActChildLaunch(**{**child.__dict__, "execution_generation": 4})
    with pytest.raises(ValueError, match="ACT_STACK_FACTORY_SCOPE_INVALID"):
        make_pick_place_act_stack(
            context, child, ros2_executable=executable(tmp_path, "ros2"),
            readiness_executable=executable(tmp_path, "act_stack_ready"),
            base_environment={},
        )
    assert not (tmp_path / "task8-live").exists()


def test_graph_clear_probe_requires_empty_exact_domain(tmp_path):
    from so101_teleop.unified.act_stack import ActStackLaunch

    ros2 = executable(tmp_path, "ros2")
    launch = ActStackLaunch(
        ros2_executable=ros2, session_id="session-290", evidence_root=tmp_path,
        ros_domain_id=176, environment={"GZ_PARTITION": "act-task8-176-campaign-290"},
    )
    calls = []
    outputs = [b"/move_group\n", b""]

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, outputs.pop(0), b"")

    probe = RosGraphClearProbe(launch, run=runner)
    assert probe() is False
    assert probe() is True
    assert calls[0][0] == [str(ros2), "node", "list", "--no-daemon"]
    assert calls[0][1]["env"]["ROS_DOMAIN_ID"] == "176"


def test_graph_clear_probe_rejects_failed_command(tmp_path):
    from so101_teleop.unified.act_stack import ActStackLaunch

    ros2 = executable(tmp_path, "ros2")
    launch = ActStackLaunch(
        ros2_executable=ros2, session_id="session-290", evidence_root=tmp_path,
        ros_domain_id=176, environment={"GZ_PARTITION": "act-task8-176-campaign-290"},
    )
    probe = RosGraphClearProbe(
        launch, run=lambda argv, **kwargs: subprocess.CompletedProcess(argv, 1, b"", b"error"),
    )
    assert probe() is False
