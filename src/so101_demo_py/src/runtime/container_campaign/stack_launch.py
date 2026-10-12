"""One explicitly namespaced ACT stack with unchanged original parameter values."""

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

import yaml

from so101_demo.runtime.container_campaign.ros_namespace import namespaced_parameters, namespace_remappings, validate_container_namespace
from so101_demo.runtime.container_campaign.retirement import _write
from so101_demo.runtime.parallel_ipc.frames import canonical_json
from so101_teleop.unified.act_stack import ActStackLaunch


@dataclass(frozen=True, slots=True)
class ContainerActStackLaunch(ActStackLaunch):
    ros_namespace: str
    readiness_timeout_s: float

    def __post_init__(self):
        ActStackLaunch.__post_init__(self)
        validate_container_namespace(self.ros_namespace)
        if (type(self.readiness_timeout_s) not in (int,float) or not math.isfinite(self.readiness_timeout_s)
                or not 0 < self.readiness_timeout_s <= 300):
            raise ValueError("CONTAINER_STACK_BUDGET_INVALID")

    def argv(self):
        return [str(self.ros2_executable), "launch", "so101_demo_py", "so101_mujoco_container_shard.launch.py",
            "headless:=true", "sensor_rendering:=true", "act_profile:=true", f"session_id:={self.session_id}",
            f"task_evidence_root:={self.evidence_root}", f"task_namespace:={self.ros_namespace}",
            f"readiness_timeout_s:={self.readiness_timeout_s}"]


def configured_actions(context):
    from ament_index_python.packages import get_package_share_directory
    from launch.actions import GroupAction
    from launch.substitutions import LaunchConfiguration
    from launch_ros.actions import PushRosNamespace, SetRemap
    from so101_demo.runtime.launch_composition.task_station import _configured_act_execution_stack_actions

    namespace = validate_container_namespace(LaunchConfiguration("task_namespace").perform(context))
    root = Path(LaunchConfiguration("task_evidence_root").perform(context))
    if not root.is_absolute() or root.resolve(strict=True) != root or not root.is_dir():
        raise ValueError("CONTAINER_STACK_ROOT_INVALID")
    configs = root / "namespace-config"
    configs.mkdir(mode=0o700)
    share = Path(get_package_share_directory("so101_demo_py"))
    manifest = {}
    for name in ("ros2_controllers.yaml", "mujoco_plugins.yaml"):
        original = (share / "config/mujoco/act" / name).read_bytes()
        scoped = yaml.safe_dump(namespaced_parameters(yaml.safe_load(original), namespace), sort_keys=False).encode()
        _write(configs, name, scoped)
        manifest[name] = dict(original_sha256=hashlib.sha256(original).hexdigest(),
                             derived_sha256=hashlib.sha256(scoped).hexdigest())
    _write(configs, "manifest.json", canonical_json(dict(schema_version=1,
        kind="ACT_SHARD_NAMESPACE_PARAMETERS", ros_namespace=namespace, files=manifest)))
    actions = _configured_act_execution_stack_actions(context,
        controller_parameters_path=configs / "ros2_controllers.yaml", plugin_parameters_path=configs / "mujoco_plugins.yaml")
    return [GroupAction([PushRosNamespace(namespace),
        *(SetRemap(src=source, dst=target) for source,target in namespace_remappings(namespace)), *actions])]


def build_launch_description():
    from ament_index_python.packages import get_package_share_directory
    from launch import LaunchDescription
    from launch.actions import DeclareLaunchArgument, OpaqueFunction
    from so101_demo.runtime.launch_composition.common import MUJOCO_CUP_KEYFRAMES

    share = Path(get_package_share_directory("so101_demo_py"))
    return LaunchDescription([DeclareLaunchArgument("headless", default_value="true", choices=("true",)),
        DeclareLaunchArgument("sensor_rendering", default_value="true", choices=("true",)),
        DeclareLaunchArgument("act_profile", default_value="true", choices=("true",)),
        DeclareLaunchArgument("session_id"), DeclareLaunchArgument("task_evidence_root"),
        DeclareLaunchArgument("task_namespace"), DeclareLaunchArgument("readiness_timeout_s"),
        DeclareLaunchArgument("mujoco_scene", default_value=str(share / "assets/mujoco/act/scene.xml")),
        DeclareLaunchArgument("mujoco_initial_keyframe", default_value="task_start", choices=MUJOCO_CUP_KEYFRAMES[:4]),
        OpaqueFunction(function=configured_actions)])
