from __future__ import annotations

import importlib
import sys

from launch import LaunchDescription
from launch.actions import ExecuteProcess

from so101_demo.runtime import launch_composition


def _runner_module():
    return importlib.import_module("so101_demo.cli.perception_pick_place_launch")


def _exit_status():
    assert hasattr(launch_composition, "PerceptionLaunchExitStatus")
    return launch_composition.PerceptionLaunchExitStatus()


def _process(command: str) -> ExecuteProcess:
    return ExecuteProcess(cmd=[sys.executable, "-c", command], output="both")


def _description(scene, perception, workflow, exit_status) -> LaunchDescription:
    assert hasattr(launch_composition, "perception_pick_place_exit_handlers")
    handlers = launch_composition.perception_pick_place_exit_handlers(
        scene,
        perception,
        workflow,
        exit_status=exit_status,
    )
    return LaunchDescription([*handlers, scene])


def test_real_launch_service_preserves_scene_failure_exit_code() -> None:
    exit_status = _exit_status()
    description = _description(
        _process("raise SystemExit(12)"),
        _process("raise SystemExit(91)"),
        _process("raise SystemExit(92)"),
        exit_status,
    )

    result = _runner_module().run_launch_description(description, exit_status)

    assert result == 12


def test_real_launch_service_preserves_workflow_failure_exit_code() -> None:
    exit_status = _exit_status()
    description = _description(
        _process("raise SystemExit(0)"),
        _process("import time; time.sleep(30)"),
        _process("raise SystemExit(23)"),
        exit_status,
    )

    result = _runner_module().run_launch_description(description, exit_status)

    assert result == 23
