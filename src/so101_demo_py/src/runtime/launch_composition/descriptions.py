"""The Gazebo and MuJoCo pick-place launch descriptions."""

from __future__ import annotations

import os
from pathlib import Path
import uuid

from ament_index_python.packages import get_package_prefix, get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    LogInfo,
    OpaqueFunction,
    Shutdown,
)
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

from so101_demo.core.policy_registry import load_policy_variant
from so101_demo.ports.capabilities import CapabilityRequirements
from so101_demo.runtime.composition import backend_capabilities
from so101_demo.runtime.launch_composition.common import MUJOCO_CUP_KEYFRAMES
from so101_demo.runtime.launch_composition.gazebo_actions import _gazebo_execute_actions
from so101_demo.runtime.launch_composition.mujoco_actions import _mujoco_execute_actions
from so101_demo.runtime.provenance import (
    installed_bundle,
)


def _configured_actions(context, *, backend: str, pick_place: bool):
    run_mode = LaunchConfiguration("run_mode").perform(context)
    execute = LaunchConfiguration("execute").perform(context).lower() == "true"
    if run_mode not in {"dry_run", "execute"}:
        raise RuntimeError(f"unsupported run_mode: {run_mode}")
    if execute != (run_mode == "execute"):
        raise RuntimeError("run_mode execute and execute:=true must be selected together")
    session_id = LaunchConfiguration("session_id").perform(context)
    if not session_id:
        raise RuntimeError("session_id must be non-empty")
    share = Path(get_package_share_directory("so101_demo_py"))
    try:
        prefix = Path(get_package_prefix("so101_demo_py"))
    except (LookupError, OSError, RuntimeError):
        # DEBUG metadata only: a missing ament index must not block an otherwise
        # functional launch that already resolved its share directory.
        prefix = None
    policy = load_policy_variant(
        LaunchConfiguration("policy_id").perform(context),
        backend,
        share,
    )
    bundle = installed_bundle()
    capabilities = backend_capabilities(backend)
    base_capabilities = CapabilityRequirements.base_execute().validate(capabilities)
    source_commit = bundle.manifest["inputs"].get("source_commit") or "unknown"
    messages = [
        LogInfo(msg=f"so101 backend={backend}"),
        LogInfo(msg=f"so101 source_commit={source_commit}"),
        LogInfo(msg="so101 source_commit_authority=DEBUG_METADATA_ONLY"),
        LogInfo(msg=f"so101 installed_prefix={prefix}"),
        LogInfo(msg=f"so101 policy_sha256={policy.policy_sha256}"),
        LogInfo(msg=f"so101 bundle_sha256={bundle.bundle_sha256}"),
        LogInfo(msg=f"so101 execute={str(execute).lower()} session_id={session_id}"),
        LogInfo(
            msg="so101 base_execute_capabilities="
            + ("accepted" if base_capabilities.accepted else "rejected")
        ),
        LogInfo(
            msg="so101 lossless_physics_step_trace="
            + str(capabilities.lossless_physics_step_trace).lower()
        ),
        LogInfo(msg=f"so101 ROS_DOMAIN_ID={os.environ.get('ROS_DOMAIN_ID', '')}"),
    ]
    if backend == "gazebo":
        messages.append(LogInfo(msg=f"so101 GZ_PARTITION={os.environ.get('GZ_PARTITION', '')}"))
    if run_mode == "dry_run":
        if not pick_place:
            return messages
        workflow = Node(
            package="so101_demo_py",
            executable="fixed_cup_pick_place",
            arguments=["--backend", backend, "--run-mode", "dry_run"],
            output="both",
            on_exit=Shutdown(reason="SO-101 dry run complete"),
        )
        return [*messages, workflow]
    if backend == "mujoco":
        return [
            *messages,
            *_mujoco_execute_actions(
                context, share, policy, session_id, include_workflow=pick_place
            ),
        ]
    if backend == "gazebo":
        return [
            *messages,
            *_gazebo_execute_actions(
                context,
                share,
                policy,
                bundle,
                session_id,
                include_workflow=pick_place,
            ),
        ]
    raise RuntimeError(f"{backend} execute graph is not registered")


def build_launch_description(*, backend: str, pick_place: bool) -> LaunchDescription:
    if backend not in {"mujoco", "gazebo"}:
        raise ValueError(f"unsupported launch backend: {backend}")
    share = Path(get_package_share_directory("so101_demo_py"))
    unique = uuid.uuid4().hex
    arguments = [
        DeclareLaunchArgument("run_mode", default_value="dry_run", choices=("dry_run", "execute")),
        DeclareLaunchArgument("execute", default_value="false", choices=("true", "false")),
        DeclareLaunchArgument("headless", default_value="true", choices=("true", "false")),
        DeclareLaunchArgument("policy_id", default_value="light_cup_wall_pick"),
        DeclareLaunchArgument("session_id", default_value=unique),
        DeclareLaunchArgument("evidence_file", default_value=f"/tmp/so101-{unique}.json"),
        DeclareLaunchArgument("readiness_timeout_s", default_value="90.0"),
    ]
    if backend == "mujoco":
        arguments.extend(
            (
                DeclareLaunchArgument(
                    "sensor_rendering",
                    default_value="auto",
                    choices=("auto", "true", "false"),
                ),
                DeclareLaunchArgument(
                    "mujoco_scene", default_value=str(share / "assets/mujoco/scene.xml")
                ),
                DeclareLaunchArgument(
                    "mujoco_initial_keyframe",
                    default_value="task_start",
                    choices=MUJOCO_CUP_KEYFRAMES,
                ),
            )
        )
    else:
        arguments.append(
            DeclareLaunchArgument(
                "gazebo_world", default_value=str(share / "assets/gazebo/world.sdf")
            )
        )
    return LaunchDescription(
        [
            *arguments,
            OpaqueFunction(
                function=_configured_actions,
                kwargs={"backend": backend, "pick_place": pick_place},
            ),
        ]
    )
