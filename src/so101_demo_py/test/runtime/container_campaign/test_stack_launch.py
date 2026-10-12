"""Container launch uses a real namespace and exact same-path stack evidence."""

import importlib
from pathlib import Path

import pytest


def test_launch_adds_explicit_namespace_without_generic_launch_alias(tmp_path):
    mod = importlib.import_module("so101_demo.runtime.container_campaign.stack_launch")
    launch = mod.ContainerActStackLaunch(ros2_executable=Path('/usr/bin/true'), session_id="session1",
        evidence_root=tmp_path, ros_domain_id=181, environment={"GZ_PARTITION":"case1"},
        ros_namespace="/act/campaign/w00", readiness_timeout_s=180.)
    argv = launch.argv()
    assert "so101_mujoco_container_shard.launch.py" in argv
    assert "task_namespace:=/act/campaign/w00" in argv
    assert f"task_evidence_root:={tmp_path}" in argv
    assert "readiness_timeout_s:=180.0" in argv
    assert launch.process_environment()["ROS_DOMAIN_ID"] == "181"


@pytest.mark.parametrize("namespace", ["/", "relative", "/bad-name"])
def test_invalid_container_namespace_cannot_form_native_command(tmp_path, namespace):
    mod = importlib.import_module("so101_demo.runtime.container_campaign.stack_launch")
    with pytest.raises(ValueError):
        mod.ContainerActStackLaunch(ros2_executable=Path('/usr/bin/true'), session_id="session1",
            evidence_root=tmp_path, ros_domain_id=181, environment={},
            ros_namespace=namespace, readiness_timeout_s=180.)
