from pathlib import Path


def test_reset_ports_expose_backend_neutral_operations() -> None:
    from so101_demo.ports.reset import (
        GoalCancellationPort,
        PhysicalObjectResetPort,
        ResetObservationPort,
        ResetPlanningScenePort,
        ResetRobotPort,
    )

    assert set(GoalCancellationPort.__protocol_attrs__) >= {
        "cancel_arm_goals",
        "cancel_gripper_goals",
    }
    assert set(PhysicalObjectResetPort.__protocol_attrs__) >= {
        "detach_task_object",
        "park_task_object",
        "restore_task_object",
    }
    assert set(ResetPlanningScenePort.__protocol_attrs__) >= {
        "detach_task_object",
        "synchronize_task_scene",
    }
    assert set(ResetRobotPort.__protocol_attrs__) >= {
        "open_gripper",
        "plan_home",
        "execute_home_and_verify",
    }
    assert set(ResetObservationPort.__protocol_attrs__) >= {
        "observe_initial",
        "verify_final",
    }


def test_reset_application_and_ports_do_not_expose_simulator_teleport() -> None:
    package = Path(__file__).parents[2] / "src"
    sources = (
        (package / "ports/reset.py").read_text(encoding="utf-8")
        + (package / "application/transactional_reset.py").read_text(encoding="utf-8")
    ).lower()
    assert "teleport" not in sources
    assert "set_pose" not in sources
    assert "gz service" not in sources
