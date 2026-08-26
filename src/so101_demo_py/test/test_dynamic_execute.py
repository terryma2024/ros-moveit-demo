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


def _mujoco_sample(
    *, sequence: int, step: int, cup_z_m: float, table_contact: bool
) -> SimpleNamespace:
    return SimpleNamespace(
        publisher_sequence=sequence,
        simulation_step=step,
        reset_epoch=0,
        object_state=SimpleNamespace(
            position_world=(0.02, -0.33, cup_z_m),
            orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
            linear_velocity_world=(0.0, 0.0, -0.0001),
            angular_velocity_world=(0.0, 0.0, 0.0),
        ),
        left_fingertip_contacts=(object(),),
        right_fingertip_contacts=(object(),),
        maximum_normal_force_n=0.5,
        other_object_contacts=(
            (SimpleNamespace(geom2="table_collision"),) if table_contact else ()
        ),
    )


class _DiagnosticIk:
    target_joints = (0.0200, -0.3130, 0.2040, 0.0010, 0.0020)

    def solve(self, *_args, **_kwargs) -> tuple[float, ...]:
        return self.target_joints

    def forward(self, joints: tuple[float, ...]) -> PoseEvidence:
        return PoseEvidence(tuple(joints[:3]), (0.0, 0.0, 0.0, 1.0))

    @staticmethod
    def orientation_error_rad(_actual: PoseEvidence, _target: PoseEvidence) -> float:
        return 0.0


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


def test_failed_micro_lift_persists_terminal_joint_tcp_and_cup_diagnostics() -> None:
    adapter = object.__new__(RosDynamicMujocoExecution)
    before = _mujoco_sample(sequence=100, step=1000, cup_z_m=0.1646, table_contact=True)
    after = _mujoco_sample(sequence=107, step=1434, cup_z_m=0.1653, table_contact=False)
    snapshots = iter((before, after))
    start_joints = (0.0200, -0.3130, 0.2000, 0.0010, 0.0020)
    terminal_joints = (0.0199, -0.3131, 0.2035, 0.0011, 0.0021)
    joint_states = iter((start_joints, terminal_joints))
    trajectory = SimpleNamespace(
        joint_trajectory=SimpleNamespace(points=(object(), object()))
    )
    adapter._snapshot = lambda: next(snapshots)
    adapter._joint_state = lambda: next(joint_states)
    adapter._ik = _DiagnosticIk()
    adapter._planning = SimpleNamespace(
        plan_joint_path=lambda *_args, **_kwargs: SimpleNamespace(
            failure=None,
            trajectory=trajectory,
        )
    )
    adapter._trajectory = SimpleNamespace(
        execute=lambda *_args, **_kwargs: ActionResult(ActionStatus.SUCCEEDED)
    )
    adapter._template = SimpleNamespace(
        position_tolerance_m=0.002,
        orientation_tolerance_rad=(0.10, 0.10, 0.10),
        velocity_scaling=0.03,
        acceleration_scaling=0.03,
        planning_timeout_s=8.0,
        planning_group="arm",
        tcp_link="so101_tcp",
    )
    adapter._initial = before
    adapter._before_micro_lift = None
    adapter._state_events = []
    adapter._document = {"state_events": adapter._state_events}
    adapter._write = lambda: None
    target = PoseEvidence((0.0200, -0.3130, 0.2040), (0.0, 0.0, 0.0, 1.0))

    with pytest.raises(RuntimeError, match="DYNAMIC_MICRO_LIFT_NOT_PROVED"):
        adapter._motion(State.MICRO_LIFT, target)

    assert len(adapter._state_events) == 1
    event = adapter._state_events[0]
    assert event["state"] == State.MICRO_LIFT.value
    assert event["validation_failure"] == "DYNAMIC_MICRO_LIFT_NOT_PROVED"
    assert event["terminal_joint_positions_rad"] == list(terminal_joints)
    assert event["terminal_fk_pose"] == pytest.approx(
        [*terminal_joints[:3], 0.0, 0.0, 0.0, 1.0]
    )
    assert event["terminal_position_error_m"] == pytest.approx(
        math.dist(terminal_joints[:3], target.position_m)
    )
    assert event["physical_cup_lift_m"] == pytest.approx(0.0007)
    assert event["physical_bilateral_contact"] is True
    assert event["physical_table_contact"] is False


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
