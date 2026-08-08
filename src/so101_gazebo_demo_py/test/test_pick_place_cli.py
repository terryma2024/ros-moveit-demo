import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from so101_gazebo_demo_py.cli import pick_place_state_machine


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


def test_live_execute_propagates_stop_after(monkeypatch, capsys, tmp_path) -> None:
    observed = {}
    monkeypatch.setenv("SO101_PY_EVIDENCE_DIR", str(tmp_path))
    monkeypatch.setattr(
        "so101_gazebo_demo_py.live_execute.run_live_execute",
        lambda evidence, stop_after=None, motion_policy=None: observed.update(
            evidence=evidence, stop_after=stop_after, motion_policy=motion_policy,
        ) or {
            "status": "CHECKPOINT_COMPLETE", "current_state": stop_after,
            "state_trace": ["IDLE", stop_after], "exit_code": 0,
        },
    )
    assert pick_place_state_machine.main([
        "--mode", "execute", "--stop-after", "VERIFY_PHYSICAL_GRASP",
    ]) == 0
    assert observed["stop_after"] == "VERIFY_PHYSICAL_GRASP"
    assert observed["motion_policy"] is None
    assert "status=CHECKPOINT_COMPLETE" in capsys.readouterr().out


def test_explicit_live_plan_only_uses_real_planner(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setenv("SO101_PY_EVIDENCE_DIR", str(tmp_path))
    calls = []
    monkeypatch.setattr(
        "so101_gazebo_demo_py.live_execute.run_live_plan_only",
        lambda evidence, state, motion_policy=None: calls.append(
            (evidence, state, motion_policy)
        ) or {
            "status": "PLAN_ONLY_COMPLETE", "current_state": state,
            "state_trace": [state], "exit_code": 0,
        },
    )
    assert pick_place_state_machine.main([
        "--mode", "plan_only", "--plan-only-state", "LIFT", "--live-runtime",
    ]) == 0
    assert calls[0][1] == "LIFT"
    assert calls[0][2] is None
    assert "status=PLAN_ONLY_COMPLETE" in capsys.readouterr().out
