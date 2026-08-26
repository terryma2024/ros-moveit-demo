from pathlib import Path

import pytest


def test_setup_exposes_only_named_fixed_and_dynamic_pick_place_entries() -> None:
    source = Path("src/so101_demo_py/setup.py").read_text(encoding="utf-8")

    assert "fixed_cup_pick_place = so101_demo.cli.fixed_cup_pick_place:main" in source
    assert "dynamic_cup_pick_place = so101_demo.cli.dynamic_cup_pick_place:main" in source
    assert '"pick_place = so101_demo.cli.pick_place:main"' not in source


def test_dynamic_execute_is_rejected_before_rclpy_import(monkeypatch, capsys) -> None:
    import builtins

    from so101_demo.cli import dynamic_cup_pick_place

    real_import = builtins.__import__

    def reject_rclpy(name, *args, **kwargs):
        if name == "rclpy" or name.startswith("rclpy."):
            raise AssertionError("rclpy must not be imported for rejected execute")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_rclpy)

    assert dynamic_cup_pick_place.main(["--mode", "execute", "--execute"]) == 1
    assert "failure=DYNAMIC_EXECUTION_NOT_QUALIFIED" in capsys.readouterr().out


def test_dynamic_mujoco_execute_dispatches_only_with_explicit_live_provenance(
    monkeypatch, tmp_path
) -> None:
    from so101_demo.cli import dynamic_cup_pick_place
    from so101_demo.ros import dynamic_runtime

    calls = []
    monkeypatch.setattr(
        dynamic_runtime,
        "run_dynamic_execute",
        lambda options: calls.append(options) or 23,
        raising=False,
    )

    result = dynamic_cup_pick_place.main(
        [
            "--backend",
            "mujoco",
            "--mode",
            "execute",
            "--execute",
            "--session-id",
            "dynamic-test",
            "--expected-reset-epoch",
            "0",
            "--evidence-root",
            str(tmp_path),
        ]
    )

    assert result == 23
    assert len(calls) == 1


def test_dynamic_cli_removes_launch_injected_ros_arguments(monkeypatch, tmp_path) -> None:
    from so101_demo.cli import dynamic_cup_pick_place
    from so101_demo.ros import dynamic_runtime

    calls = []
    monkeypatch.setattr(
        dynamic_runtime,
        "run_dynamic_execute",
        lambda options: calls.append(options) or 29,
        raising=False,
    )

    assert (
        dynamic_cup_pick_place.main(
            [
                "--backend",
                "mujoco",
                "--mode",
                "execute",
                "--execute",
                "--session-id",
                "dynamic-test",
                "--expected-reset-epoch",
                "0",
                "--evidence-root",
                str(tmp_path),
                "--ros-args",
            ]
        )
        == 29
    )
    assert len(calls) == 1


def test_dynamic_cli_still_rejects_unknown_application_argument(capsys) -> None:
    from so101_demo.cli import dynamic_cup_pick_place

    with pytest.raises(SystemExit) as error:
        dynamic_cup_pick_place.main(["--unknown-application-option"])
    assert error.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err


def test_fixed_entrypoint_module_does_not_import_dynamic_or_rclpy() -> None:
    source = Path("src/so101_demo_py/src/cli/fixed_cup_pick_place.py").read_text(encoding="utf-8")

    assert "dynamic" not in source
    assert "rclpy" not in source


def test_dynamic_gazebo_runtime_uses_simulation_clock() -> None:
    source = Path("src/so101_demo_py/src/ros/dynamic_runtime.py").read_text(
        encoding="utf-8"
    )

    assert 'Parameter("use_sim_time", value=True)' in source
