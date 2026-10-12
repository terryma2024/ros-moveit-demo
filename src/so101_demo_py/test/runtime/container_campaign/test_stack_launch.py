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


def test_actual_configured_launch_writes_scoped_parameters_and_group(tmp_path, monkeypatch):
    import json
    import yaml
    from launch import LaunchContext
    from launch.actions import GroupAction
    from ament_index_python import packages

    mod = importlib.import_module("so101_demo.runtime.container_campaign.stack_launch")
    share = Path(__file__).parents[3]
    monkeypatch.setattr(packages,"get_package_share_directory",lambda name: str(share))
    context = LaunchContext()
    context.launch_configurations.update(dict(session_id="session1",task_evidence_root=str(tmp_path),
        task_namespace="/act/campaign/w00",headless="true",sensor_rendering="true",act_profile="true",
        readiness_timeout_s="180",mujoco_scene=str(share/'assets/mujoco/act/scene.xml'),mujoco_initial_keyframe="task_start"))
    actions = mod.configured_actions(context)
    assert len(actions)==1 and isinstance(actions[0],GroupAction)
    manifest=json.loads((tmp_path/'namespace-config/manifest.json').read_bytes())
    assert manifest['ros_namespace']=="/act/campaign/w00"
    original=yaml.safe_load((share/'config/mujoco/act/ros2_controllers.yaml').read_bytes())
    actual=yaml.safe_load((tmp_path/'namespace-config/ros2_controllers.yaml').read_bytes())
    assert all(actual['/act/campaign/w00/'+name]==values for name,values in original.items())
