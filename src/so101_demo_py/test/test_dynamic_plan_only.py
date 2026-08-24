from so101_demo.core.domain import State
from so101_demo.ports.evidence import PoseEvidence
from so101_demo.ports.robot_control import JointStateEvidence, PlanResult


class FakeProvider:
    def target_for(self, state: State) -> PoseEvidence:
        assert state is State.MOVE_ABOVE_OBJECT
        return PoseEvidence((0.02, -0.28, 0.28), (0.0, 0.0, 0.0, 1.0))


class FakeControl:
    def __init__(self) -> None:
        self.requests = []
        self.execute_calls = 0

    def plan_tcp_motion(self, request):
        self.requests.append(request)
        start = JointStateEvidence(("1", "2"), (0.0, 0.0), 1.0)
        terminal = JointStateEvidence(("1", "2"), (0.1, 0.2), 2.0)
        return PlanResult(True, start_state=start, terminal_state=terminal, trajectory=object())

    def execute(self, _plan):
        self.execute_calls += 1
        raise AssertionError("plan-only must never execute")


def test_plans_exactly_one_shared_workflow_state_without_execution() -> None:
    from so101_demo.application.dynamic_plan_only import DynamicPlanningOptions, plan_dynamic_state

    control = FakeControl()
    result = plan_dynamic_state(
        state=State.MOVE_ABOVE_OBJECT,
        provider=FakeProvider(),
        control=control,
        options=DynamicPlanningOptions(
            planning_frame="world",
            planning_group="arm",
            tcp_link="so101_tcp",
            position_tolerance_m=0.002,
            orientation_tolerance_rad=(0.1, 0.1, 0.1),
            planning_timeout_s=5.0,
            velocity_scaling=0.03,
            acceleration_scaling=0.03,
        ),
    )

    assert result.accepted
    assert len(control.requests) == 1
    request = control.requests[0]
    assert request.target_pose.position_m == (0.02, -0.28, 0.28)
    assert request.planning_frame == "world"
    assert request.planning_group == "arm"
    assert request.tcp_link == "so101_tcp"
    assert request.position_tolerance_m == 0.002
    assert request.velocity_scaling == 0.03
    assert control.execute_calls == 0


def test_rejects_a_non_motion_state_before_calling_planner() -> None:
    import pytest

    from so101_demo.application.dynamic_plan_only import (
        DynamicPlanOnlyError,
        DynamicPlanningOptions,
        plan_dynamic_state,
    )

    control = FakeControl()
    with pytest.raises(DynamicPlanOnlyError, match="PLAN_ONLY_STATE_UNSUPPORTED"):
        plan_dynamic_state(
            state=State.OPEN_GRIPPER,
            provider=FakeProvider(),
            control=control,
            options=DynamicPlanningOptions(
                "world", "arm", "so101_tcp", 0.002, (0.1, 0.1, 0.1), 5.0, 0.03, 0.03
            ),
        )
    assert control.requests == []
