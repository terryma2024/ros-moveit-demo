"""Shared backend-selectable Planning Scene command."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ament_index_python.packages import get_package_share_directory

from ..application.scene_setup import execute_task_scene_operation
from ..control.planning_scene.task_scene import RosTaskScenePort
from ..core.task_geometry import GeometryContractError, load_task_geometry
from ..ports.planning_scene import SceneCommandReceipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scene_setup")
    parser.add_argument("--backend", choices=("mujoco", "gazebo"), default="mujoco")
    parser.add_argument(
        "operation",
        nargs="?",
        choices=("setup", "observe", "attach", "detach", "upsert"),
        default="setup",
    )
    return parser


def execute_scene_operation(backend: str, operation: str) -> SceneCommandReceipt:
    import rclpy

    share = Path(get_package_share_directory("so101_demo_py"))
    try:
        geometry = load_task_geometry(share / "assets/common/geometry-manifest.yaml")
    except GeometryContractError as error:
        return SceneCommandReceipt(
            backend,
            "LOAD_MANIFEST",
            False,
            "SCENE_MANIFEST_INVALID",
            {"message": str(error)},
        )
    rclpy.init()
    node = rclpy.create_node(f"so101_{backend}_scene_setup")
    try:
        timeout_s = float(node.declare_parameter("readiness_timeout_s", 30.0).value)
        port = RosTaskScenePort(node, backend, timeout_s)
        return execute_task_scene_operation(port, geometry, operation)
    except Exception as error:
        return SceneCommandReceipt(
            backend,
            "COMMAND",
            False,
            "SCENE_COMMAND_FAILED",
            {"message": str(error)},
        )
    finally:
        node.destroy_node()
        rclpy.shutdown()


def main(arguments: list[str] | None = None) -> int:
    options, _ros_arguments = build_parser().parse_known_args(arguments)
    receipt = execute_scene_operation(options.backend, options.operation)
    print(json.dumps(asdict(receipt), sort_keys=True), flush=True)
    return 0 if receipt.success else 1
