import json
from pathlib import Path


def _receipt(*, backend: str = "gazebo", success: bool = True):
    from so101_demo.ports.planning_scene import SceneCommandReceipt

    return SceneCommandReceipt(
        backend=backend,
        phase="READ_BACK",
        success=success,
        failure_code=None if success else "SCENE_READBACK_MISMATCH",
        evidence={"primitive_counts": {"table": 1, "pedestal": 1, "plastic_cup": 13}},
    )


def test_cli_defaults_to_compatible_mujoco_setup(monkeypatch, capsys) -> None:
    from so101_demo.cli import scene_setup

    calls = []
    monkeypatch.setattr(
        scene_setup,
        "execute_scene_operation",
        lambda backend, operation: calls.append((backend, operation))
        or _receipt(backend=backend),
    )

    assert scene_setup.main([]) == 0
    assert calls == [("mujoco", "setup")]
    assert json.loads(capsys.readouterr().out)["success"] is True


def test_cli_dispatches_every_gazebo_scene_operation(monkeypatch) -> None:
    from so101_demo.cli import scene_setup

    calls = []
    monkeypatch.setattr(
        scene_setup,
        "execute_scene_operation",
        lambda backend, operation: calls.append((backend, operation))
        or _receipt(backend=backend),
    )

    for operation in ("setup", "observe", "attach", "detach", "upsert"):
        assert scene_setup.main(["--backend", "gazebo", operation]) == 0

    assert calls == [("gazebo", operation) for operation in (
        "setup",
        "observe",
        "attach",
        "detach",
        "upsert",
    )]


def test_cli_returns_nonzero_and_stable_failure(monkeypatch, capsys) -> None:
    from so101_demo.cli import scene_setup

    monkeypatch.setattr(
        scene_setup,
        "execute_scene_operation",
        lambda backend, operation: _receipt(backend=backend, success=False),
    )

    assert scene_setup.main(["--backend", "gazebo", "observe"]) == 1
    document = json.loads(capsys.readouterr().out)
    assert document["phase"] == "READ_BACK"
    assert document["failure_code"] == "SCENE_READBACK_MISMATCH"


def test_setup_entrypoint_is_the_shared_cli() -> None:
    setup_source = Path("src/so101_demo_py/setup.py").read_text(encoding="utf-8")
    assert "scene_setup = so101_demo.cli.scene_setup:main" in setup_source
