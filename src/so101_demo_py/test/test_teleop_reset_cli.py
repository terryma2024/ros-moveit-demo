import json


def test_cli_defaults_to_compatible_mujoco(monkeypatch, capsys) -> None:
    from so101_demo.cli import teleop_reset

    receipt = type(
        "Receipt",
        (),
        {
            "simulation_session_id": "session-a",
            "old_epoch": 1,
            "new_epoch": 2,
            "simulation_step": 0,
            "keyframe": "task_start",
        },
    )()
    calls = []
    monkeypatch.setattr(
        teleop_reset,
        "transactional_reset",
        lambda session_id, keyframe: calls.append((session_id, keyframe)) or receipt,
    )

    assert teleop_reset.main(["--session-id", "session-a"]) == 0
    assert calls == [("session-a", "task_start")]
    assert json.loads(capsys.readouterr().out)["backend"] == "mujoco"


def test_cli_dispatches_gazebo_transaction_and_writes_evidence(
    monkeypatch, tmp_path, capsys
) -> None:
    from so101_demo.cli import teleop_reset
    from so101_demo.ports.reset import TransactionalResetReceipt

    receipt = TransactionalResetReceipt(
        backend="gazebo",
        session_id="session-gz",
        success=True,
        phase="VERIFY_FINAL",
        failure_code=None,
        steps=(),
        evidence={"completed_phases": ["VERIFY_FINAL"]},
    )
    calls = []
    monkeypatch.setattr(
        teleop_reset,
        "execute_gazebo_reset",
        lambda session_id: calls.append(session_id) or receipt,
    )
    evidence = tmp_path / "reset.json"

    assert teleop_reset.main(
        [
            "--backend",
            "gazebo",
            "--session-id",
            "session-gz",
            "--evidence-file",
            str(evidence),
        ]
    ) == 0
    assert calls == ["session-gz"]
    assert json.loads(evidence.read_text())["phase"] == "VERIFY_FINAL"
    assert json.loads(capsys.readouterr().out)["success"] is True


def test_cli_gazebo_failure_is_nonzero_with_stable_fields(monkeypatch, capsys) -> None:
    from so101_demo.cli import teleop_reset
    from so101_demo.ports.reset import TransactionalResetReceipt

    monkeypatch.setattr(
        teleop_reset,
        "execute_gazebo_reset",
        lambda _session_id: TransactionalResetReceipt(
            backend="gazebo",
            session_id="session-gz",
            success=False,
            phase="DETACH_PHYSICAL",
            failure_code="RESET_GAZEBO_DETACH_VERIFY_FAILED",
            steps=(),
            evidence={"attached": True},
        ),
    )

    assert teleop_reset.main(
        ["--backend", "gazebo", "--session-id", "session-gz"]
    ) == 1
    document = json.loads(capsys.readouterr().out)
    assert document["phase"] == "DETACH_PHYSICAL"
    assert document["failure_code"] == "RESET_GAZEBO_DETACH_VERIFY_FAILED"
