from pathlib import Path
from types import SimpleNamespace

import subprocess


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


def test_task_station_readiness_requires_graph_joint_sample_and_scene_observe() -> None:
    from so101_demo.cli.mujoco_rgbd_batch import _wait_for_task_station

    calls = []

    def runner(argv, **kwargs):
        calls.append((tuple(argv), kwargs))
        command = tuple(argv[2:])
        if command[:2] == ("node", "list"):
            return subprocess.CompletedProcess(argv, 0, "/so101_move_group\n", "")
        if command[:2] == ("service", "list"):
            return subprocess.CompletedProcess(
                argv,
                0,
                "/apply_planning_scene\n/get_planning_scene\n/plan_kinematic_path\n",
                "",
            )
        if command[:2] == ("topic", "echo"):
            return subprocess.CompletedProcess(argv, 0, "name:\n- '1'\n", "")
        if command[:3] == ("run", "so101_demo_py", "scene_setup"):
            return subprocess.CompletedProcess(argv, 0, '{"success": true}\n', "")
        raise AssertionError(argv)

    _wait_for_task_station(1.0, runner=runner, sleep=lambda _seconds: None)

    commands = [call[0][2:] for call in calls]
    assert ("node", "list", "--no-daemon", "--spin-time", "0.2") in commands
    assert ("service", "list", "--no-daemon", "--spin-time", "0.2") in commands
    assert any(command[:3] == ("topic", "echo", "--once") for command in commands)
    assert ("run", "so101_demo_py", "scene_setup", "--backend", "mujoco", "observe") in commands


def test_task_station_readiness_does_not_accept_only_a_move_group_process() -> None:
    from so101_demo.cli.mujoco_rgbd_batch import _wait_for_task_station

    ticks = iter((0.0, 0.0, 2.0, 2.0))

    def runner(argv, **kwargs):
        del kwargs
        command = tuple(argv[2:])
        if command[:2] == ("node", "list"):
            return subprocess.CompletedProcess(argv, 0, "/so101_move_group\n", "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    try:
        _wait_for_task_station(
            1.0,
            runner=runner,
            monotonic=lambda: next(ticks),
            sleep=lambda _seconds: None,
        )
    except TimeoutError as error:
        assert "joint states, MoveIt services, and planning scene" in str(error)
    else:
        raise AssertionError("a bare move_group process must not satisfy readiness")
