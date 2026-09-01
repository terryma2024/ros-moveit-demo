import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


def _ros2_arguments(argv: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    command = tuple(argv)
    if command[:1] == ("ros2",):
        return command[1:]
    if len(command) >= 2 and Path(command[1]).name == "ros2":
        return command[2:]
    raise AssertionError(f"unsupported ros2 command prefix: {command!r}")


def _ros2_arguments(argv) -> tuple[str, ...]:
    command = tuple(argv)
    for index, token in enumerate(command):
        if token in {"run", "topic"}:
            return command[index:]
    raise AssertionError(f"ROS 2 subcommand missing: {command}")


def test_cli_defaults_visible_and_requires_explicit_attach_session(tmp_path: Path) -> None:
    from so101_demo.cli.mujoco_rgbd_batch import build_parser

    options = build_parser().parse_args(
        [
            "--points",
            str(tmp_path / "points.yaml"),
            "--batch-id",
            "batch-1",
            "--session-id",
            "sim-a",
            "--evidence-root",
            str(tmp_path / "evidence"),
        ]
    )
    assert options.headless is False
    assert options.attach_existing_stack is False


def test_cli_exit_is_nonzero_when_any_point_failed() -> None:
    from so101_demo.application.task_batch import BatchStatus
    from so101_demo.cli.mujoco_rgbd_batch import result_exit_code

    assert result_exit_code(SimpleNamespace(status=BatchStatus.SUCCEEDED)) == 0
    assert result_exit_code(SimpleNamespace(status=BatchStatus.FAILED)) == 1
    assert result_exit_code(SimpleNamespace(status=BatchStatus.CANCELLED)) == 1


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_task_station_readiness_requires_graph_joint_sample_and_scene_observe(
    monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    from so101_demo.application import qualification_stack
    from so101_demo.cli.mujoco_rgbd_batch import _wait_for_task_station

    monkeypatch.setattr(qualification_stack.sys, "platform", platform)
    monkeypatch.setattr(
        qualification_stack.shutil,
        "which",
        lambda _name: "/opt/ros/jazzy/bin/ros2",
    )
    calls = []

    def runner(argv, **kwargs):
        calls.append((tuple(argv), kwargs))
        command = _ros2_arguments(argv)
        if command[:3] == ("run", "so101_demo_py", "motion_stack_ready"):
            return subprocess.CompletedProcess(
                argv,
                0,
                '{"ready": true, "phase": "READY"}\n',
                "",
            )
        if command[:2] == ("topic", "echo"):
            return subprocess.CompletedProcess(argv, 0, "name:\n- '1'\n", "")
        if command[:3] == ("run", "so101_demo_py", "scene_setup"):
            return subprocess.CompletedProcess(argv, 0, '{"success": true}\n', "")
        raise AssertionError(argv)

    _wait_for_task_station(1.0, runner=runner, sleep=lambda _seconds: None)

    commands = [_ros2_arguments(call[0]) for call in calls]
    assert any(
        command[:3] == ("run", "so101_demo_py", "motion_stack_ready")
        for command in commands
    )
    assert any(command[:3] == ("topic", "echo", "--once") for command in commands)
    assert ("run", "so101_demo_py", "scene_setup", "--backend", "mujoco", "observe") in commands


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_task_station_readiness_reports_the_failed_stage(
    monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    from so101_demo.application import qualification_stack
    from so101_demo.cli.mujoco_rgbd_batch import _wait_for_task_station

    monkeypatch.setattr(qualification_stack.sys, "platform", platform)
    monkeypatch.setattr(
        qualification_stack.shutil,
        "which",
        lambda _name: "/opt/ros/jazzy/bin/ros2",
    )

    def runner(argv, **kwargs):
        del kwargs
        command = _ros2_arguments(argv)
        assert command[:3] == ("run", "so101_demo_py", "motion_stack_ready")
        return subprocess.CompletedProcess(
            argv,
            1,
            '{"ready": false, "phase": "CONTROLLERS"}\n',
            "controller unavailable",
        )

    try:
        _wait_for_task_station(1.0, runner=runner, sleep=lambda _seconds: None)
    except TimeoutError as error:
        assert "controllers_and_moveit" in str(error)
        assert "CONTROLLERS" in str(error)
    else:
        raise AssertionError("a failed readiness stage must not be accepted")


def test_task_station_readiness_default_budget_covers_macos_cold_start() -> None:
    import inspect

    from so101_demo.cli.mujoco_rgbd_batch import _wait_for_task_station

    assert inspect.signature(_wait_for_task_station).parameters["timeout_s"].default >= 240.0
