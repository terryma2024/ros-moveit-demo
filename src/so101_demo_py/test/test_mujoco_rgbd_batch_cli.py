from pathlib import Path
from types import SimpleNamespace


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
