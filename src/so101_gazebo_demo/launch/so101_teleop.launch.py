"""Launch the simulation-only SO-101 Teleop server after Web preflight."""

from __future__ import annotations

import os
from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node



def ensure_web_bundle(*args, **kwargs):
    from so101_teleop.web_bundle import ensure_web_bundle as implementation
    return implementation(*args, **kwargs)


def validate_web_bundle(*args, **kwargs):
    from so101_teleop.web_bundle import validate_web_bundle as implementation
    return implementation(*args, **kwargs)


def _source_directory(explicit: str) -> Path | None:
    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    if os.environ.get("SO101_TELEOP_WEB_SOURCE"):
        candidates.append(Path(os.environ["SO101_TELEOP_WEB_SOURCE"]).expanduser())
    candidates.append(Path(__file__).resolve().parents[1] / "web")
    try:
        module_file = __import__("so101_teleop.web_bundle", fromlist=["__file__"]).__file__
        candidates.append(Path(module_file).resolve().parents[1] / "web")
    except (ImportError, AttributeError):
        pass
    for candidate in candidates:
        resolved = candidate.resolve()
        if (resolved / "package.json").is_file():
            return resolved
    return None


def _installed_bundle() -> Path:
    from ament_index_python.packages import get_package_share_directory
    return Path(get_package_share_directory("so101_gazebo_demo")) / "web"


def _as_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"build_web_if_needed must be true or false, got {value!r}")


def launch_setup(context):
    explicit_source = LaunchConfiguration("web_source_dir").perform(context)
    build_if_needed = _as_bool(LaunchConfiguration("build_web_if_needed").perform(context))
    source = _source_directory(explicit_source)
    try:
        if source is not None:
            web_root = ensure_web_bundle(source, build_if_needed)
        else:
            web_root = validate_web_bundle(_installed_bundle())
    except Exception as error:
        raise RuntimeError(
            f"SO-101 Teleop Web preflight failed: {error}. "
            "Provide web_source_dir:=/path/to/so101_gazebo_demo/web or a valid installed bundle."
        ) from error

    return [Node(
        package="so101_gazebo_demo",
        executable="so101_teleop_server.py",
        output="screen",
        additional_env={
            "SO101_TELEOP_BIND": LaunchConfiguration("bind_address"),
            "SO101_TELEOP_PORT": LaunchConfiguration("port"),
            "SO101_WORLD_NAME": LaunchConfiguration("world_name"),
            "SO101_TCP_FRAME": LaunchConfiguration("tcp_frame"),
            "SO101_SIMULATION_SESSION_ID": LaunchConfiguration("simulation_session_id"),
            "SO101_TELEOP_WEB_ROOT": str(web_root),
            "GZ_PARTITION": LaunchConfiguration("gz_partition"),
        },
    )]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("bind_address", default_value="127.0.0.1"),
        DeclareLaunchArgument("port", default_value="8000"),
        DeclareLaunchArgument("simulation_only", default_value="true"),
        DeclareLaunchArgument("world_name", default_value="so101_pick_place"),
        DeclareLaunchArgument("tcp_frame", default_value="so101_tcp"),
        DeclareLaunchArgument("simulation_session_id", default_value="teleop-launch-session"),
        DeclareLaunchArgument("gz_partition", default_value=os.environ.get("GZ_PARTITION", "")),
        DeclareLaunchArgument("build_web_if_needed", default_value="true"),
        DeclareLaunchArgument("web_source_dir", default_value=""),
        OpaqueFunction(function=launch_setup),
    ])
