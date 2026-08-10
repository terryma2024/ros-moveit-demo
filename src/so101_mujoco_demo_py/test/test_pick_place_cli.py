from so101_mujoco_demo_py import cli


def test_dry_run_cli_prints_machine_comparable_result(capsys, tmp_path) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    assert cli.main(["--mode", "dry_run", "--checkpoint", str(checkpoint)]) == 0
    output = capsys.readouterr().out
    assert "status=DONE" in output
    assert "current_state=DONE" in output
    assert "transition_count=19" in output
    assert "state_trace=IDLE,PREPARE_OPEN_GRIPPER,MOVE_ABOVE_OBJECT" in output
    assert checkpoint.is_file()


def test_injected_failure_has_nonzero_exit_and_stable_code(capsys) -> None:
    assert cli.main(["--mode", "dry_run", "--fail-at", "DESCEND"]) == 1
    assert "failure=INJECTED_FAILURE" in capsys.readouterr().out


def test_plan_only_runs_offline_and_execute_fails_closed_until_task_12(capsys) -> None:
    assert cli.main(["--mode", "plan_only", "--plan-only-state", "LIFT"]) == 0
    assert "status=PLAN_ONLY_COMPLETE" in capsys.readouterr().out
    assert cli.main(["--mode", "execute"]) == 1
    output = capsys.readouterr().out
    assert "failure=LIVE_RUNTIME_NOT_IMPLEMENTED" in output
