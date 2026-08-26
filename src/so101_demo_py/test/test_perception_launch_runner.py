from __future__ import annotations

import importlib
import sys

from launch.actions import ExecuteProcess, OpaqueFunction
from so101_demo.runtime import launch_composition

from launch import LaunchDescription


def _runner_module():
    return importlib.import_module("so101_demo.cli.perception_pick_place_launch")


def _exit_status():
    assert hasattr(launch_composition, "PerceptionLaunchExitStatus")
    return launch_composition.PerceptionLaunchExitStatus()


def _process(command: str) -> ExecuteProcess:
    return ExecuteProcess(cmd=[sys.executable, "-c", command], output="both")


def _description(
    scene,
    perception,
    workflow,
    exit_status,
    *,
    successful_one_shots=(),
) -> LaunchDescription:
    assert hasattr(launch_composition, "perception_pick_place_exit_handlers")
    handlers = launch_composition.perception_pick_place_exit_handlers(
        scene,
        perception,
        workflow,
        required_long_lived=(("synthetic perception", perception),),
        successful_one_shots=successful_one_shots,
        exit_status=exit_status,
    )
    return LaunchDescription(
        [*handlers, *(action for _label, action in successful_one_shots), scene]
    )


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


def test_real_launch_service_preserves_required_long_lived_failure_exit_code() -> None:
    exit_status = _exit_status()
    description = _description(
        _process("raise SystemExit(0)"),
        _process("raise SystemExit(17)"),
        _process("import time; time.sleep(30)"),
        exit_status,
    )

    result = _runner_module().run_launch_description(description, exit_status)

    assert result == 17


def test_clean_workflow_ignores_one_shot_teardown_exit() -> None:
    exit_status = _exit_status()
    spawner = _process("import time; time.sleep(30)")
    description = _description(
        _process("raise SystemExit(0)"),
        _process("import time; time.sleep(30)"),
        _process("raise SystemExit(0)"),
        exit_status,
        successful_one_shots=(("synthetic spawner", spawner),),
    )

    result = _runner_module().run_launch_description(description, exit_status)

    assert result == 0


def test_clean_child_status_does_not_mask_launch_service_failure() -> None:
    exit_status = _exit_status()

    def record_clean_then_fail(_context):
        exit_status.record(0)
        raise RuntimeError("teardown handler failed")

    description = LaunchDescription([OpaqueFunction(function=record_clean_then_fail)])

    result = _runner_module().run_launch_description(description, exit_status)

    assert result == 1
