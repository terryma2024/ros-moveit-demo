from dataclasses import fields
from types import SimpleNamespace

import pytest
from so101_demo.ports.cup_scene_observation import CupSceneObservation
from so101_demo.ports.evidence import PoseEvidence
from test_dynamic_pick import _sample, _template


def _observation(x: float = 0.02, *, attached: bool = False) -> CupSceneObservation:
    pose = PoseEvidence((x, -0.28, 0.165), (0.0, 0.0, 0.0, 1.0))
    return CupSceneObservation(pose, 1.0, pose, 1.1, attached)


def test_accepts_topic_simulator_and_moveit_pose_within_tolerance() -> None:
    from so101_demo.application.cup_pose_preflight import validate_cup_scene

    validate_cup_scene(_sample(), _observation(), _template())


def test_scene_observation_exposes_optional_mujoco_identity() -> None:
    names = {field.name for field in fields(CupSceneObservation)}
    assert {"simulation_session_id", "reset_epoch", "paused"} <= names


@pytest.mark.parametrize(
    ("changes", "code"),
    (
        ({"simulation_session_id": None}, "CUP_POSE_SCENE_IDENTITY_MISSING"),
        ({"reset_epoch": None}, "CUP_POSE_SCENE_IDENTITY_MISSING"),
        ({"paused": None}, "CUP_POSE_SCENE_IDENTITY_MISSING"),
        ({"simulation_session_id": "other"}, "CUP_POSE_SCENE_SESSION_MISMATCH"),
        ({"reset_epoch": 4}, "CUP_POSE_SCENE_RESET_EPOCH_MISMATCH"),
        ({"paused": True}, "CUP_POSE_SCENE_PAUSED"),
    ),
)
def test_mujoco_identity_gate_rejects_invalid_truth(changes, code) -> None:
    from so101_demo.application.cup_pose_preflight import (
        CupPosePreflightError,
        validate_mujoco_scene_identity,
    )

    values = {
        "simulation_session_id": "task-5",
        "reset_epoch": 3,
        "paused": False,
        **changes,
    }
    observation = SimpleNamespace(**values)

    with pytest.raises(CupPosePreflightError) as caught:
        validate_mujoco_scene_identity(
            observation,
            expected_session_id="task-5",
            expected_reset_epoch=3,
        )

    assert caught.value.code == code


def test_rejects_any_scene_divergence_or_attachment() -> None:
    from so101_demo.application.cup_pose_preflight import CupPosePreflightError, validate_cup_scene

    with pytest.raises(CupPosePreflightError, match="topic_vs_simulator"):
        validate_cup_scene(_sample(), _observation(0.05), _template())
    with pytest.raises(CupPosePreflightError, match="world object"):
        validate_cup_scene(_sample(), _observation(attached=True), _template())


def test_second_gate_detects_scene_change_after_planning() -> None:
    from so101_demo.application.cup_pose_preflight import CupPosePreflightError
    from so101_demo.application.dynamic_plan_only import (
        DynamicPlanningOptions,
        plan_dynamic_state_with_scene_gates,
    )
    from test_dynamic_plan_only import FakeControl, FakeProvider

    class Scene:
        def __init__(self) -> None:
            self.values = iter((_observation(), _observation(0.05)))

        def observe(self, _timeout_s):
            return next(self.values)

    with pytest.raises(CupPosePreflightError, match="topic_vs_simulator"):
        plan_dynamic_state_with_scene_gates(
            state=__import__("so101_demo.core.domain", fromlist=["State"]).State.MOVE_ABOVE_OBJECT,
            provider=FakeProvider(),
            control=FakeControl(),
            options=DynamicPlanningOptions(
                "world", "arm", "so101_tcp", 0.002, (0.1, 0.1, 0.1), 5.0, 0.03, 0.03
            ),
            scene=Scene(),
            sample=_sample(),
            template=_template(),
        )
