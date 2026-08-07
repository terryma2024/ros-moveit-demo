import os
from pathlib import Path
import subprocess
import sys


PACKAGE = Path(__file__).parents[1]


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(PACKAGE)
    return subprocess.run(
        [sys.executable, "-m", "so101_gazebo_demo_py.cli.pick_place_state_machine", *arguments],
        text=True, capture_output=True, env=environment, check=False,
    )


def test_dry_run_cli_prints_machine_comparable_result(tmp_path: Path) -> None:
    result = run_cli("--mode", "dry_run", "--checkpoint", str(tmp_path / "checkpoint.json"))
    assert result.returncode == 0
    assert "status=DONE" in result.stdout
    assert "current_state=DONE" in result.stdout
    assert "transition_count=19" in result.stdout
    assert "state_trace=IDLE,PREPARE_OPEN_GRIPPER,MOVE_ABOVE_OBJECT" in result.stdout
    assert (tmp_path / "checkpoint.json").is_file()


def test_cli_syntax_and_injected_failure_exit_codes() -> None:
    assert run_cli("--mode", "unknown").returncode == 2
    failed = run_cli("--mode", "dry_run", "--fail-at", "DESCEND")
    assert failed.returncode == 1
    assert "failure=INJECTED_FAILURE" in failed.stdout
