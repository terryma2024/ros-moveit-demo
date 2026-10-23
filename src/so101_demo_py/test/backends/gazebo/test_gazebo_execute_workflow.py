import pytest
from so101_demo.core.domain import ActionResult, ActionStatus, Failure, FailureCategory

PHASES = (
    "PREPARE_OPEN_GRIPPER",
    "MOVE_ABOVE_OBJECT",
    "DESCEND",
    "GRASP_CLOSE",
    "ATTACH_PHYSICAL",
    "ATTACH_MOVEIT",
    "LIFT",
    "MOVE_ABOVE_PLACE",
    "DESCEND_TO_PLACE",
    "RELEASE_OPEN",
    "DETACH_PHYSICAL",
    "DETACH_MOVEIT",
    "RETREAT",
)


class Operations:
    def __init__(self, fail_at=None):
        self.fail_at = fail_at
        self.calls = []

    def _run(self, phase, detail=None):
        self.calls.append((phase, detail))
        if phase == self.fail_at:
            return ActionResult(
                ActionStatus.FAILED,
                Failure(FailureCategory.EXECUTION, f"{phase}_FAILED", phase),
            )
        return ActionResult(ActionStatus.SUCCEEDED)

    def arm(self, phase, state):
        return self._run(phase, state)

    def gripper(self, phase, target):
        return self._run(phase, target)

    def physical(self, phase, attach):
        return self._run(phase, attach)

    def scene(self, phase, attach):
        return self._run(phase, attach)


def _policy():
    return type(
        "Policy",
        (),
        {
            "gripper": type(
                "Gripper",
                (),
                {"preopen_q6": 0.4, "grasp_close_q6": -0.04, "release_q6": 0.75},
            )(),
            "states": {name: object() for name in (
                "MOVE_ABOVE_OBJECT",
                "DESCEND",
                "LIFT",
                "MOVE_ABOVE_PLACE",
                "DESCEND_TO_PLACE",
                "RETREAT",
            )},
        },
    )()


def test_normal_gazebo_workflow_runs_every_phase_and_succeeds() -> None:
    from so101_demo.backends.gazebo.workflow import execute_gazebo_workflow

    operations = Operations()
    boundary = execute_gazebo_workflow(_policy(), operations)

    assert [phase for phase, _detail in operations.calls] == list(PHASES)
    assert boundary.phase == "RETREAT"
    assert boundary.action.status is ActionStatus.SUCCEEDED
    assert boundary.evidence_valid


@pytest.mark.parametrize("failure_at", PHASES)
def test_normal_gazebo_workflow_reports_real_first_failure(failure_at: str) -> None:
    from so101_demo.backends.gazebo.workflow import execute_gazebo_workflow

    operations = Operations(failure_at)
    boundary = execute_gazebo_workflow(_policy(), operations)

    index = PHASES.index(failure_at)
    assert [phase for phase, _detail in operations.calls] == list(PHASES[: index + 1])
    assert boundary.phase == failure_at
    assert boundary.action.status is ActionStatus.FAILED
    assert boundary.action.failure.code == f"{failure_at}_FAILED"
    assert boundary.evidence_valid


def test_success_is_not_rewritten_as_incomplete_or_invalid() -> None:
    from so101_demo.backends.gazebo.workflow import execute_gazebo_workflow

    boundary = execute_gazebo_workflow(_policy(), Operations())

    assert boundary.action.failure is None
    assert boundary.phase == "RETREAT"
