import json


def test_cli_defaults_to_compatible_mujoco(monkeypatch, capsys) -> None:
    from so101_demo.cli import teleop_reset
    from so101_demo.ports.planning_scene import SceneCommandReceipt

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
    scene_receipt = SceneCommandReceipt(
        backend="mujoco",
        phase="READ_BACK",
        success=True,
        failure_code=None,
        evidence={"world_ids": ["pedestal", "plastic_cup", "table"]},
    )
    calls = []
    monkeypatch.setattr(
        teleop_reset,
        "execute_mujoco_reset",
        lambda session_id, keyframe: (
            calls.append((session_id, keyframe)) or (receipt, scene_receipt)
        ),
    )

    assert teleop_reset.main(["--session-id", "session-a"]) == 0
    assert calls == [("session-a", "task_start")]
    document = json.loads(capsys.readouterr().out)
    assert document["backend"] == "mujoco"
    assert document["requested_object_position_world_m"] == [0.02, -0.28, 0.165]


def test_cli_sends_custom_cup_position_and_records_evidence(
    monkeypatch, capsys
) -> None:
    from so101_demo.cli import teleop_reset
    from so101_demo.ports.planning_scene import SceneCommandReceipt

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
    scene_receipt = SceneCommandReceipt(
        backend="mujoco",
        phase="READ_BACK",
        success=True,
        failure_code=None,
        evidence={"world_ids": ["pedestal", "plastic_cup", "table"]},
    )
    calls = []

    def execute(session_id, *, keyframe, cup_position_world_m=None):
        calls.append((session_id, keyframe, cup_position_world_m))
        return receipt, scene_receipt

    monkeypatch.setattr(teleop_reset, "execute_mujoco_reset", execute)

    assert teleop_reset.main(
        [
            "--session-id",
            "session-a",
            "--cup-position-world-m",
            "-0.03",
            "-0.28",
            "0.165",
        ]
    ) == 0

    assert calls == [("session-a", "task_start", (-0.03, -0.28, 0.165))]
    document = json.loads(capsys.readouterr().out)
    assert document["requested_object_position_world_m"] == [-0.03, -0.28, 0.165]


def test_mujoco_reset_builds_exactly_one_plastic_cup_override(monkeypatch) -> None:
    from so101_demo.cli import teleop_reset
    from so101_demo.ports.planning_scene import SceneCommandReceipt

    reset_receipt = object()
    calls = []

    def reset(session_id, **kwargs):
        calls.append((session_id, kwargs))
        return reset_receipt

    monkeypatch.setattr(teleop_reset, "transactional_reset", reset)
    monkeypatch.setattr(
        teleop_reset,
        "execute_scene_operation",
        lambda *_args: SceneCommandReceipt(
            backend="mujoco",
            phase="READ_BACK",
            success=True,
            failure_code=None,
            evidence={},
        ),
    )

    receipt, _scene = teleop_reset.execute_mujoco_reset(
        "sim-a",
        keyframe="task_start",
        cup_position_world_m=(-0.03, -0.28, 0.165),
    )

    assert receipt is reset_receipt
    assert calls[0][0] == "sim-a"
    assert calls[0][1]["expected_object_position"] == (-0.03, -0.28, 0.165)
    overrides = calls[0][1]["free_joint_overrides"]
    assert len(overrides) == 1
    assert overrides[0].name == "plastic_cup"
    assert overrides[0].position_world_m == (-0.03, -0.28, 0.165)


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
