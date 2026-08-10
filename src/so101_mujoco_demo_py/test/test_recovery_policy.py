from so101_mujoco_demo_py.domain import ActionStatus, State
from so101_mujoco_demo_py.recovery.coordinator import WorldResetAction
from so101_mujoco_demo_py.recovery.policy import (
    RecoveryEvidence,
    RecoveryPolicy,
    recovery_evidence_from_simulation,
)
from so101_mujoco_demo_py.simulation.types import (
    ContactEvidence,
    ObjectState,
    ResetReceipt,
    SimulationEvidence,
)


def test_recovery_skips_unobserved_side_effects() -> None:
    state = RecoveryEvidence(
        simulator_task_object_constrained=False,
        moveit_task_object_attached=False,
    )
    assert RecoveryPolicy().path_for(State.LIFT, state) == (State.RECOVER_RETREAT,)


def test_recovery_reverses_observed_scene_then_simulator_constraint() -> None:
    state = RecoveryEvidence(
        simulator_task_object_constrained=True,
        moveit_task_object_attached=True,
    )
    path = RecoveryPolicy().path_for(State.LIFT, state)
    assert path.index(State.RECOVER_DETACH_GAZEBO) < path.index(State.RECOVER_DETACH_MOVEIT)
    assert path[-1] is State.RECOVER_RETREAT


def test_recovery_holds_physically_grasped_object_until_support_is_proved() -> None:
    for supported in (False, None):
        held = RecoveryEvidence(
            task_object_supported=supported,
            gripper_task_object_contact=True,
            simulator_task_object_constrained=False,
            moveit_task_object_attached=True,
        )
        assert RecoveryPolicy().path_for(State.LIFT, held) == ()


def test_recovery_evidence_uses_task5_observation_and_reset_protocols() -> None:
    contact = ContactEvidence(
        7,
        8,
        "plastic_cup",
        "cup",
        9,
        10,
        "table",
        "table_top",
        (0.0, 0.0, 0.16),
        (0.0, 0.0, 1.0),
        -1e-6,
        0.2,
    )
    evidence = SimulationEvidence(
        1.0,
        "world",
        5,
        10,
        3,
        "session-a",
        False,
        ObjectState(
            7,
            "plastic_cup",
            (0.0, 0.0, 0.16),
            (0.0, 0.0, 0.0, 1.0),
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
        ),
        True,
        -1e-6,
        0.2,
        False,
        (),
        (),
        (contact,),
    )
    converted = recovery_evidence_from_simulation(
        evidence, moveit_task_object_attached=False, intended_support_collision="table_top"
    )
    assert converted == RecoveryEvidence(False, False, True, False)

    class Reset:
        def __init__(self) -> None:
            self.keyframes = []

        def reset(self, keyframe: str) -> ResetReceipt:
            self.keyframes.append(keyframe)
            return ResetReceipt(3, 4, keyframe, 0, "session-a")

    reset = Reset()
    assert WorldResetAction(reset).run().status is ActionStatus.SUCCEEDED
    assert reset.keyframes == ["task_start"]
