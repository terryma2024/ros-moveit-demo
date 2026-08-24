import math
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from so101_demo.application.dynamic_execute import build_dynamic_actions
from so101_demo.core.domain import ActionResult, ActionStatus, RunMode, RunRequest, State
from so101_demo.core.dynamic_pick import DYNAMIC_MOTION_STATES
from so101_demo.core.runner import StateMachineRunner
from so101_demo.ports.evidence import PoseEvidence
from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution


@dataclass
class RecordingExecutionPort:
    calls: list[tuple[State, PoseEvidence | None]] = field(default_factory=list)

    def perform(self, state: State, target: PoseEvidence | None) -> ActionResult:
        self.calls.append((state, target))
        return ActionResult(ActionStatus.SUCCEEDED)


class Targets:
    def __init__(self) -> None:
        self.values = {
            state: PoseEvidence((float(index), 0.0, 0.2), (0.0, 0.0, 0.0, 1.0))
            for index, state in enumerate(sorted(DYNAMIC_MOTION_STATES, key=lambda item: item.value))
        }

    def target_for(self, state: State) -> PoseEvidence:
        return self.values[state]


class WorldObserver:
    def snapshot(self):
        return SimpleNamespace(
            simulation_session_id="dynamic-test",
            publisher_sequence=42,
            reset_epoch=0,
        )


def test_dynamic_execute_uses_shared_workflow_and_topic_resolved_motion_targets() -> None:
    port = RecordingExecutionPort()
    targets = Targets()
    runner = StateMachineRunner(
        build_dynamic_actions(port, targets),
        session_id="dynamic-test",
        world_observer=WorldObserver(),
    )

    result = runner.run(RunRequest(mode=RunMode.EXECUTE))

    assert result.current_state is State.DONE
    assert result.status.value == "DONE"
    assert result.state_trace[:4] == (
        State.IDLE,
        State.PREPARE_OPEN_GRIPPER,
        State.MOVE_ABOVE_OBJECT,
        State.DESCEND,
    )
    assert result.state_trace[-1] is State.DONE
    called = dict(port.calls)
    for state in DYNAMIC_MOTION_STATES & set(called):
        assert called[state] is targets.values[state]
    for state, target in port.calls:
        if state not in DYNAMIC_MOTION_STATES:
            assert target is None


def test_dynamic_execute_registers_every_shared_workflow_action() -> None:
    actions = build_dynamic_actions(RecordingExecutionPort(), Targets())

    from so101_demo.core.workflow import SO101_WORKFLOW

    assert set(actions) == SO101_WORKFLOW.action_states


def test_dynamic_mujoco_descent_allows_only_touch_collision_before_planning() -> None:
    adapter = object.__new__(RosDynamicMujocoExecution)
    adapter._initial = object()
    adapter._document = {}
    adapter._write = lambda: None
    calls: list[tuple[str, object]] = []
    adapter._set_touch_collision = lambda allowed: calls.append(("touch", allowed))
    adapter._motion = lambda state, target: calls.append(("motion", state))
    target = PoseEvidence((0.02, -0.28, 0.20), (0.0, 0.0, 0.0, 1.0))

    result = adapter.perform(State.DESCEND, target)

    assert result.status is ActionStatus.SUCCEEDED
    assert calls == [("touch", True), ("motion", State.DESCEND)]


@pytest.mark.parametrize("state", [State.RETREAT, State.RECOVER_RETREAT])
def test_dynamic_mujoco_retreat_allows_cup_touch_only_during_motion(state: State) -> None:
    adapter = object.__new__(RosDynamicMujocoExecution)
    adapter._initial = object()
    adapter._document = {}
    adapter._write = lambda: None
    calls: list[tuple[str, object]] = []
    adapter._set_touch_collision = lambda allowed: calls.append(("touch", allowed))
    adapter._motion = lambda actual_state, target: calls.append(("motion", actual_state))
    target = PoseEvidence((-0.07, -0.23, 0.28), (0.0, 0.0, 0.0, 1.0))

    result = adapter.perform(state, target)

    assert result.status is ActionStatus.SUCCEEDED
    assert calls == [("touch", True), ("motion", state), ("touch", False)]


def test_micro_lift_allows_initial_table_contact_but_transport_does_not() -> None:
    assert not RosDynamicMujocoExecution._reject_carried_table_contact(State.MICRO_LIFT, True)
    assert RosDynamicMujocoExecution._reject_carried_table_contact(State.LIFT, True)
    assert not RosDynamicMujocoExecution._reject_carried_table_contact(State.LIFT, False)


def test_pose_interpolation_reaches_target_and_normalizes_quaternion() -> None:
    start = PoseEvidence((0.0, 0.0, 0.2), (0.0, 0.0, 0.0, 1.0))
    target = PoseEvidence((0.1, -0.2, 0.3), (0.0, 0.0, 1.0, 0.0))

    midpoint = RosDynamicMujocoExecution._interpolate_pose(start, target, 0.5)
    endpoint = RosDynamicMujocoExecution._interpolate_pose(start, target, 1.0)

    assert midpoint.position_m == (0.05, -0.1, 0.25)
    assert sum(value * value for value in midpoint.orientation_xyzw) == pytest.approx(1.0)
    assert endpoint.position_m == target.position_m
    assert endpoint.orientation_xyzw == target.orientation_xyzw


def test_upright_tilt_ignores_cylindrical_cup_yaw() -> None:
    yaw = 0.33
    yaw_only = (0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0))
    roll = 0.20
    rolled = (math.sin(roll / 2.0), 0.0, 0.0, math.cos(roll / 2.0))

    assert RosDynamicMujocoExecution._upright_tilt_rad(yaw_only) == pytest.approx(0.0)
    assert RosDynamicMujocoExecution._upright_tilt_rad(rolled) == pytest.approx(roll)
