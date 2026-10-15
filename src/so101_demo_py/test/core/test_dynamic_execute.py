import json
import math
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest
from so101_demo.application.dynamic_execute import build_dynamic_actions
from so101_demo.core.domain import (
    ActionResult,
    ActionStatus,
    Failure,
    FailureCategory,
    RunMode,
    RunRequest,
    State,
)
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
            for index, state in enumerate(
                sorted(DYNAMIC_MOTION_STATES, key=lambda item: item.value)
            )
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


def _joint_message(positions: tuple[float, ...], stamp_ns: int) -> SimpleNamespace:
    return SimpleNamespace(
        name=list(RosDynamicMujocoExecution._ARM_JOINTS),
        position=list(positions),
        header=SimpleNamespace(
            stamp=SimpleNamespace(
                sec=stamp_ns // 1_000_000_000,
                nanosec=stamp_ns % 1_000_000_000,
            )
        ),
    )


def _finish_adapter():
    adapter = object.__new__(RosDynamicMujocoExecution)
    adapter._document = {}
    adapter._state_events = []
    adapter._planning_attempts = []
    adapter._final_samples = []
    adapter._release_marker_sequence = None
    adapter._scene_readback = None
    adapter._expected_reset_epoch = 0
    adapter._write = lambda: None
    return adapter


def test_actual_dynamic_child_scene_calls_retain_full_request_response_bounds():
    from moveit_msgs.srv import ApplyPlanningScene
    from test_task_scene_builder import _geometry
    from so101_demo.control.planning_scene.task_scene import make_task_scene

    class Client:
        def wait_for_service(self, **kwargs):
            return True

        def call_async(self, request):
            return SimpleNamespace(done=lambda: True,
                                   result=lambda: ApplyPlanningScene.Response(success=True))

    adapter = object.__new__(RosDynamicMujocoExecution)
    adapter._apply_scene = Client()
    adapter._get_scene = object()
    adapter._node = object()
    adapter._scene_service_calls = []
    request = ApplyPlanningScene.Request(scene=make_task_scene(_geometry()))
    assert adapter._call(adapter._apply_scene, request, 0.1, "DYNAMIC_DETACH_SYNC").success
    record, = adapter._scene_service_calls
    assert record["service"] == "/apply_planning_scene"
    assert record["phase"] == "DYNAMIC_DETACH_SYNC"
    assert record["request"]["scene"]["world"]["collision_objects"][2]["id"] == "plastic_cup"
    assert record["response"] == {"success": True}
    assert 0 < record["request_monotonic_ns"] <= record["response_monotonic_ns"]
    assert "simulation_step" not in record and "sim_time_s" not in record


@pytest.mark.parametrize("change", ["positive", "wrong_pose", "wrong_dimension", "wrong_color"])
def test_actual_dynamic_detach_verifies_full_source_derived_geometry(change):
    from dataclasses import replace
    from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene
    from so101_demo.core.simulation.types import SimulationEvidence, ObjectState
    from so101_demo.core.task_geometry import Pose7
    from so101_demo.control.planning_scene.task_scene import make_task_scene
    from test_task_scene_builder import _geometry

    base = _geometry()
    cup_pose = (0.04, -0.28, 0.165, 0.0, 0.0, 0.0, 1.0)
    source = SimulationEvidence(
        simulation_time_s=1.25, frame_id="world", publisher_sequence=9, simulation_step=625,
        reset_epoch=1, simulation_session_id="s", paused=False,
        object_state=ObjectState(1, "plastic_cup", cup_pose[:3], cup_pose[3:],
                                 (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        has_contact=False, minimum_signed_distance_m=0.0, maximum_normal_force_n=0.0,
        truncated=False, left_fingertip_contacts=(), right_fingertip_contacts=(), other_object_contacts=())
    expected = replace(base, objects=(*base.objects[:2], replace(base.objects[2], pose=Pose7(cup_pose))))
    response_scene = make_task_scene(expected)
    response_scene.robot_state.attached_collision_objects = []
    if change == "wrong_pose":
        response_scene.world.collision_objects[2].pose.position.x += 0.01
    elif change == "wrong_dimension":
        response_scene.world.collision_objects[2].primitives[0].dimensions[0] += 0.01
    elif change == "wrong_color":
        response_scene.object_colors[2].color.r = 0.0
    adapter = object.__new__(RosDynamicMujocoExecution)
    adapter._task_geometry = base
    adapter._apply_scene, adapter._get_scene = object(), object()
    adapter._snapshot = lambda: source
    adapter._supported_release_preflight = lambda: source
    adapter._touch_collision_allowed = False
    adapter._session_id, adapter._expected_reset_epoch = "s", 1
    adapter._document = {}
    adapter._write = lambda: None
    # This geometry-only fixture assumes release safety at its explicit seam.
    # The separate supported-release tests exercise that preflight itself.
    adapter._release_runtime_policy = {"safety_release": {"support_distance_max_m": 0.002}}
    adapter._execution_policy = {"state_max_age_s": 0.5}
    adapter._monotonic = lambda: 10.0
    from so101_demo.core.simulation.types import ReceivedSimulationEvidence
    adapter._selected_release_source = ReceivedSimulationEvidence(source, 10.0)
    records, calls = [], []
    adapter._record = lambda *args, **kwargs: records.append(kwargs)

    def call(client, request, *_, before_dispatch=None):
        if before_dispatch is not None:
            before_dispatch()
        calls.append(request)
        return (ApplyPlanningScene.Response(success=True) if client is adapter._apply_scene else
                GetPlanningScene.Response(scene=response_scene))

    adapter._call = call
    if change == "positive":
        adapter._detach_or_sync(State.DETACH_MOVEIT)
        assert len(records) == 1
        assert adapter._scene_readback["geometry_verification"]["mismatches"] == []
        assert adapter._scene_readback["source_physics"]["publisher_sequence"] == 9
        assert calls[0].scene.world.collision_objects[0].pose.position.x == 0.04
    else:
        with pytest.raises(RuntimeError, match="DYNAMIC_DETACH_SYNC_GEOMETRY_MISMATCH"):
            adapter._detach_or_sync(State.DETACH_MOVEIT)
        assert records == []
    retained, = adapter._document["scene_transactions"]
    assert retained["source_physics"]["publisher_sequence"] == 9
    assert retained["source_physics"]["object_state"]["position_world"] == cup_pose[:3]
    assert retained["expected_geometry"]["objects"][2]["pose"]["values"] == cup_pose


def test_the_detach_names_the_source_taken_last_with_no_manifest_write_between_it_and_the_request():
    """The named physics source is acquired immediately before the apply is dispatched: the manifest write that used to sit between
    the snapshot and the request (slow under IO load, so the source aged past the Recorder's 100 ms window) now follows the call."""
    from dataclasses import replace
    from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene
    from so101_demo.core.simulation.types import SimulationEvidence, ObjectState
    from so101_demo.core.task_geometry import Pose7
    from so101_demo.control.planning_scene.task_scene import make_task_scene
    from test_task_scene_builder import _geometry

    base = _geometry()
    cup_pose = (0.04, -0.28, 0.165, 0.0, 0.0, 0.0, 1.0)

    def evidence(sequence):
        return SimulationEvidence(
            simulation_time_s=1.25 + sequence * 0.02, frame_id="world", publisher_sequence=sequence,
            simulation_step=600 + sequence, reset_epoch=1, simulation_session_id="s", paused=False,
            object_state=ObjectState(1, "plastic_cup", cup_pose[:3], cup_pose[3:], (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
            has_contact=False, minimum_signed_distance_m=0.0, maximum_normal_force_n=0.0,
            truncated=False, left_fingertip_contacts=(), right_fingertip_contacts=(), other_object_contacts=())

    expected = replace(base, objects=(*base.objects[:2], replace(base.objects[2], pose=Pose7(cup_pose))))
    response_scene = make_task_scene(expected)
    response_scene.robot_state.attached_collision_objects = []
    adapter = object.__new__(RosDynamicMujocoExecution)
    adapter._task_geometry = base
    adapter._apply_scene, adapter._get_scene = object(), object()
    events, taken = [], []

    def snapshot():
        taken.append(evidence(len(taken) + 1))
        events.append(("snapshot", taken[-1].publisher_sequence))
        return taken[-1]

    adapter._snapshot = snapshot
    adapter._supported_release_preflight = snapshot
    adapter._touch_collision_allowed = False
    adapter._session_id, adapter._expected_reset_epoch = "s", 1
    adapter._document = {}
    adapter._write = lambda: events.append(("write",))
    adapter._release_runtime_policy = {"safety_release": {"support_distance_max_m": 0.002}}
    adapter._execution_policy = {"state_max_age_s": 0.5}
    adapter._monotonic = lambda: 10.0
    from so101_demo.core.simulation.types import ReceivedSimulationEvidence
    adapter._selected_release_source = ReceivedSimulationEvidence(evidence(1), 10.0)
    adapter._record = lambda *args, **kwargs: None

    def call(client, request, *_, before_dispatch=None):
        if client is adapter._apply_scene:
            events.append(("apply", adapter._scene_op_source["publisher_sequence"]))
        return (ApplyPlanningScene.Response(success=True) if client is adapter._apply_scene else
                GetPlanningScene.Response(scene=response_scene))

    adapter._call = call
    adapter._detach_or_sync(State.DETACH_MOVEIT)

    before_apply = events[:events.index(next(item for item in events if item[0] == "apply"))]
    named = next(item for item in events if item[0] == "apply")[1]
    assert before_apply and before_apply[-1][0] == "snapshot", "nothing but the snapshot precedes the request"
    assert named == before_apply[-1][1], "the request names the source acquired last"
    assert ("write",) in events[events.index(("apply", named)):], "the transaction is still persisted, after the call"
    retained, = adapter._document["scene_transactions"]
    assert retained["source_physics"]["publisher_sequence"] == named


def test_finish_records_explicit_no_action_authority_for_idle_failure():
    adapter = _finish_adapter()
    adapter._snapshot = lambda: pytest.fail("pre-action failure must not require physics")
    adapter._scene_membership = lambda: pytest.fail("pre-action failure must not require scene")
    result = SimpleNamespace(
        status=SimpleNamespace(value="ERROR"),
        current_state=State.ERROR,
        transition_count=1,
        state_trace=(State.IDLE, State.ERROR),
        failure=Failure(FailureCategory.EXECUTION, "EARLY_FAILURE", "injected"),
    )

    adapter.finish(result)

    assert adapter._document["failure_evidence"] == {
        "failure_boundary_state": "IDLE",
        "physical_action_proven_absent": True,
        "terminal_sample": None,
        "planning_scene_readback": None,
        "capture_errors": [],
    }


def test_finish_captures_fresh_physics_and_scene_after_possible_motion():
    adapter = _finish_adapter()
    adapter._state_events.append({
        "state": "PREPARE_OPEN_GRIPPER",
        "before": RosDynamicMujocoExecution._evidence(
            _mujoco_sample(sequence=10, step=10, cup_z_m=0.1648, table_contact=True)
        ),
        "after": RosDynamicMujocoExecution._evidence(
            _mujoco_sample(sequence=11, step=11, cup_z_m=0.1648, table_contact=True)
        ),
    })
    terminal = _mujoco_sample(sequence=12, step=12, cup_z_m=0.1648, table_contact=True)
    adapter._snapshot = lambda: terminal
    adapter._scene_membership = lambda: ([], {"plastic_cup": 13})
    result = SimpleNamespace(
        status=SimpleNamespace(value="ERROR"),
        current_state=State.ERROR,
        transition_count=4,
        state_trace=(
            State.IDLE, State.PREPARE_OPEN_GRIPPER,
            State.MOVE_ABOVE_OBJECT, State.RECOVER_RETREAT, State.ERROR,
        ),
        failure=Failure(FailureCategory.EXECUTION, "PLAN_FAILED", "injected"),
    )

    adapter.finish(result)

    evidence = adapter._document["failure_evidence"]
    assert evidence["failure_boundary_state"] == "MOVE_ABOVE_OBJECT"
    assert evidence["physical_action_proven_absent"] is False
    assert evidence["terminal_sample"]["publisher_sequence"] == 12
    assert evidence["planning_scene_readback"] == {
        "attached_object_ids": [],
        "world_primitive_counts": {"plastic_cup": 13},
    }
    assert evidence["capture_errors"] == []


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


def test_dynamic_manifest_identity_fields_are_paired_and_backward_compatible() -> None:
    assert RosDynamicMujocoExecution._workflow_identity_fields(None, None) == {}
    assert RosDynamicMujocoExecution._workflow_identity_fields("w1", "r1") == {
        "workflow_id": "w1",
        "request_id": "r1",
    }
    with pytest.raises(ValueError, match="provenance is incomplete"):
        RosDynamicMujocoExecution._workflow_identity_fields("w1", None)


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


def test_joint_state_waits_for_a_generation_after_the_execution_boundary() -> None:
    adapter = object.__new__(RosDynamicMujocoExecution)
    stale = (0.01, 0.02, 0.03, 0.04, 0.05)
    fresh = (0.11, 0.12, 0.13, 0.14, 0.15)
    adapter._positions = {}
    adapter._joint_state_generation = 0
    adapter._joint_state_source_stamp_ns = None
    adapter._joint_state_received_monotonic_s = None
    adapter._on_joint_state(_joint_message(stale, 1_000_000_100))
    boundary_generation = adapter._joint_state_generation
    progress_calls = 0

    def progress() -> None:
        nonlocal progress_calls
        progress_calls += 1
        adapter._on_joint_state(_joint_message(fresh, 1_000_000_200))

    adapter._progress = progress

    actual = adapter._joint_state(after_generation=boundary_generation)

    assert actual == fresh
    assert progress_calls == 1
    assert adapter._joint_state_generation == boundary_generation + 1
    assert adapter._joint_state_source_stamp_ns == 1_000_000_200
    assert adapter._joint_state_received_monotonic_s is not None


def test_unproved_micro_lift_is_an_audit_diagnostic_and_persists_terminal_joint_tcp_and_cup_facts(
    tmp_path,
) -> None:
    adapter = object.__new__(RosDynamicMujocoExecution)
    before = _mujoco_sample(sequence=100, step=1000, cup_z_m=0.1646, table_contact=True)
    after = _mujoco_sample(sequence=107, step=1434, cup_z_m=0.1653, table_contact=False)
    snapshots = iter((before, after))
    start_joints = (0.0200, -0.3130, 0.2000, 0.0010, 0.0020)
    terminal_joints = (0.0199, -0.3131, 0.2035, 0.0011, 0.0021)
    joint_states = iter((start_joints, terminal_joints, terminal_joints))
    trajectory = SimpleNamespace(
        joint_trajectory=SimpleNamespace(
            joint_names=list(RosDynamicMujocoExecution._ARM_JOINTS),
            points=(
                SimpleNamespace(positions=start_joints),
                SimpleNamespace(positions=_DiagnosticIk.target_joints),
            ),
        )
    )
    adapter._snapshot = lambda: next(snapshots)
    adapter._positions = dict(zip(RosDynamicMujocoExecution._ARM_JOINTS, start_joints))  # measured start == plan start
    adapter._joint_state_generation = 4
    adapter._joint_state_source_stamp_ns = 1_000_000_100
    adapter._joint_state_received_monotonic_s = 2.0

    def joint_state(*_args, after_generation=None, **_kwargs):
        value = next(joint_states)
        if after_generation is not None:
            adapter._joint_state_generation = after_generation + 1
            adapter._joint_state_source_stamp_ns += 100
            adapter._joint_state_received_monotonic_s += 0.01
        return value

    adapter._joint_state = joint_state
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
    adapter._planning_attempts = []
    adapter._document = {
        "state_events": adapter._state_events,
        "planning_attempts": adapter._planning_attempts,
    }
    adapter._evidence_file = tmp_path / "failed-micro-lift.json"
    target = PoseEvidence((0.0200, -0.3130, 0.2040), (0.0, 0.0, 0.0, 1.0))

    adapter._motion(State.MICRO_LIFT, target)  # audit-only (D3): the state no longer fails

    assert len(adapter._state_events) == 1
    event = adapter._state_events[0]
    assert event["state"] == State.MICRO_LIFT.value
    assert event["validation_failure"] is None
    diagnostic, = adapter._document["process_diagnostics"]
    assert diagnostic["code"] == "DYNAMIC_MICRO_LIFT_NOT_PROVED" and diagnostic["audit_only"] is True
    assert diagnostic["facts"] == {"physical_cup_lift_m": pytest.approx(0.0007),
                                   "bilateral_contact": True, "table_contact": False}
    assert event["terminal_joint_positions_rad"] == list(terminal_joints)
    assert event["terminal_fk_pose"] == pytest.approx([*terminal_joints[:3], 0.0, 0.0, 0.0, 1.0])
    assert event["terminal_position_error_m"] == pytest.approx(
        math.dist(terminal_joints[:3], target.position_m)
    )
    assert event["terminal_joint_state_generation"] > 4
    assert event["terminal_joint_state_source_stamp_ns"] > 1_000_000_100
    assert event["terminal_joint_state_received_monotonic_s"] > 2.0
    assert event["physical_cup_lift_m"] == pytest.approx(0.0007)
    assert event["physical_bilateral_contact"] is True
    assert event["physical_table_contact"] is False
    assert event["cartesian_corridor_receipts"][0]["accepted"] is True
    assert adapter._planning_attempts[-1]["kind"] == "actual_moveit_cartesian_corridor"
    persisted = json.loads(adapter._evidence_file.read_text(encoding="utf-8"))
    assert persisted["state_events"] == adapter._state_events


def test_dynamic_motion_rejects_sampled_tcp_detour_before_execution(tmp_path) -> None:
    adapter = object.__new__(RosDynamicMujocoExecution)
    start = (0.0, 0.0, 0.20, 0.0, 0.0)
    target = PoseEvidence((0.0, 0.0, 0.26), (0.0, 0.0, 0.0, 1.0))
    trajectory = SimpleNamespace(
        joint_trajectory=SimpleNamespace(
            joint_names=list(RosDynamicMujocoExecution._ARM_JOINTS),
            points=(
                SimpleNamespace(positions=start),
                SimpleNamespace(positions=(0.02, 0.0, 0.23, 0.0, 0.0)),
                SimpleNamespace(positions=(0.0, 0.0, 0.26, 0.0, 0.0)),
            ),
        )
    )
    adapter._snapshot = lambda: _mujoco_sample(
        sequence=100, step=1000, cup_z_m=0.165, table_contact=False
    )
    adapter._joint_state = lambda *_args, **_kwargs: start
    adapter._joint_state_generation = 4
    adapter._joint_state_source_stamp_ns = 1
    adapter._joint_state_received_monotonic_s = 1.0
    adapter._ik = _DiagnosticIk()
    adapter._ik.target_joints = (0.0, 0.0, 0.26, 0.0, 0.0)
    adapter._planning = SimpleNamespace(
        plan_joint_path=lambda *_args, **_kwargs: SimpleNamespace(
            failure=None, trajectory=trajectory
        )
    )
    executed = []
    adapter._trajectory = SimpleNamespace(execute=lambda *_args, **_kwargs: executed.append(True))
    adapter._template = SimpleNamespace(
        position_tolerance_m=0.002,
        orientation_tolerance_rad=(0.10, 0.10, 0.10),
        velocity_scaling=0.03,
        acceleration_scaling=0.03,
        planning_timeout_s=8.0,
        planning_group="arm",
        tcp_link="so101_tcp",
    )
    adapter._initial = adapter._snapshot()
    adapter._before_micro_lift = None
    adapter._state_events = []
    adapter._planning_attempts = []
    adapter._document = {
        "state_events": adapter._state_events,
        "planning_attempts": adapter._planning_attempts,
    }
    adapter._evidence_file = tmp_path / "corridor-rejection.json"

    with pytest.raises(RuntimeError, match="CARTESIAN_CORRIDOR_DEVIATION"):
        adapter._motion(State.LIFT, target)

    assert executed == []
    assert adapter._planning_attempts[-1]["accepted"] is False
    assert adapter._planning_attempts[-1]["failure_code"] == ("CARTESIAN_CORRIDOR_DEVIATION")


def test_dynamic_early_table_contact_is_an_audit_diagnostic_and_the_force_limit_still_cancels(tmp_path) -> None:
    """REPLACED_BY: early table contact no longer cancels the trajectory (D3); only the force limit does."""

    adapter = object.__new__(RosDynamicMujocoExecution)
    contact = SimpleNamespace(
        geom1="bottom_collision", geom2="table_collision",
        position_world=(0.01, -0.20, 0.12), signed_distance_m=-0.0004,
        normal_force_n=1.25,
    )
    trigger = _mujoco_sample(sequence=101, step=1001, cup_z_m=0.227, table_contact=True)
    trigger.other_object_contacts = (contact,)
    adapter._monitor_sample = lambda: trigger  # the monitor reads the latest sample without the blocking _snapshot
    adapter._positions = {**{str(index): 0.0 for index in range(1, 6)}, "6": -0.0485}
    adapter._joint_state_received_monotonic_s = 2.0
    adapter._planning_attempts = []
    adapter._document = {"planning_attempts": adapter._planning_attempts}
    adapter._evidence_file = tmp_path / "dynamic-execute-manifest.json"

    adapter._motion_monitor(State.MOVE_ABOVE_PLACE)()  # does not raise

    persisted = json.loads(adapter._evidence_file.read_text(encoding="utf-8"))
    assert "monitor_violation" not in persisted
    diagnostic, = persisted["process_diagnostics"]
    assert diagnostic["code"] == "DYNAMIC_EARLY_TABLE_CONTACT"
    assert diagnostic["state"] == State.MOVE_ABOVE_PLACE.value
    assert diagnostic["audit_only"] is True
    assert diagnostic["sample"]["publisher_sequence"] == 101
    assert diagnostic["sample"]["cup_position_world_m"] == [0.02, -0.33, 0.227]
    assert diagnostic["contacts"]["other"] == [{
        "geom1": "bottom_collision", "geom2": "table_collision",
        "position_world_m": [0.01, -0.20, 0.12],
        "signed_distance_m": -0.0004, "normal_force_n": 1.25,
    }]

    forced = _mujoco_sample(sequence=102, step=1002, cup_z_m=0.227, table_contact=True)
    forced.maximum_normal_force_n = 12.0
    adapter._monitor_sample = lambda: forced
    with pytest.raises(RuntimeError, match="DYNAMIC_FORCE_LIMIT_EXCEEDED"):
        adapter._motion_monitor(State.MOVE_ABOVE_PLACE)()
    adapter._write()
    persisted = json.loads(adapter._evidence_file.read_text(encoding="utf-8"))
    violation = persisted["monitor_violation"]
    assert violation["state"] == State.MOVE_ABOVE_PLACE.value
    assert violation["reason"] == "DYNAMIC_FORCE_LIMIT_EXCEEDED"
    assert violation["sample"]["publisher_sequence"] == 102
    assert violation["last_joint_positions_rad"]["6"] == -0.0485

    adapter._record_monitor_violation(
        State.RECOVER_LIFT_TO_SAFE_HEIGHT, "DYNAMIC_FORCE_LIMIT_EXCEEDED", forced
    )
    adapter._write()
    persisted = json.loads(adapter._evidence_file.read_text(encoding="utf-8"))
    assert persisted["monitor_violation"]["state"] == State.MOVE_ABOVE_PLACE.value
    assert [item["state"] for item in persisted["monitor_violations"]] == [
        State.MOVE_ABOVE_PLACE.value,
        State.RECOVER_LIFT_TO_SAFE_HEIGHT.value,
    ]


def test_dynamic_motion_scores_bounded_moveit_candidates_and_executes_one(
    tmp_path,
) -> None:
    adapter = object.__new__(RosDynamicMujocoExecution)
    start = (0.0, 0.0, 0.20, 0.0, 0.0)
    target_joints = (0.0, 0.0, 0.26, 0.0, 0.0)
    target = PoseEvidence((0.0, 0.0, 0.26), (0.0, 0.0, 0.0, 1.0))

    def trajectory(midpoint):
        return SimpleNamespace(
            joint_trajectory=SimpleNamespace(
                joint_names=list(RosDynamicMujocoExecution._ARM_JOINTS),
                points=(
                    SimpleNamespace(positions=start),
                    SimpleNamespace(positions=midpoint),
                    SimpleNamespace(positions=target_joints),
                ),
            )
        )

    unsafe = trajectory((0.10, 0.0, 0.23, 0.0, 0.0))
    safe = trajectory((0.0, 0.0, 0.23, 0.0, 0.0))
    planned = iter((unsafe, safe, safe, safe))
    planning_calls = []

    def plan(*_args, **_kwargs):
        planning_calls.append(True)
        return SimpleNamespace(failure=None, trajectory=next(planned))

    snapshots = iter(
        (
            _mujoco_sample(sequence=100, step=1000, cup_z_m=0.165, table_contact=False),
            _mujoco_sample(sequence=110, step=1100, cup_z_m=0.225, table_contact=False),
        )
    )
    joint_states = iter((start, target_joints, target_joints))
    adapter._positions = dict(zip(RosDynamicMujocoExecution._ARM_JOINTS, start))  # measured start == plan start
    adapter._snapshot = lambda: next(snapshots)
    adapter._joint_state_generation = 4
    adapter._joint_state_source_stamp_ns = 1_000_000_100
    adapter._joint_state_received_monotonic_s = 2.0

    def joint_state(*_args, after_generation=None, **_kwargs):
        value = next(joint_states)
        if after_generation is not None:
            adapter._joint_state_generation = after_generation + 1
        return value

    adapter._joint_state = joint_state
    adapter._ik = _DiagnosticIk()
    adapter._ik.target_joints = target_joints
    adapter._planning = SimpleNamespace(plan_joint_path=plan)
    executed = []
    adapter._trajectory = SimpleNamespace(
        execute=lambda candidate, *_args, **_kwargs: (
            executed.append(candidate) or ActionResult(ActionStatus.SUCCEEDED)
        )
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
    adapter._initial = next(
        iter((_mujoco_sample(sequence=90, step=900, cup_z_m=0.165, table_contact=True),))
    )
    adapter._before_micro_lift = None
    adapter._state_events = []
    adapter._planning_attempts = []
    adapter._document = {
        "state_events": adapter._state_events,
        "planning_attempts": adapter._planning_attempts,
    }
    adapter._evidence_file = tmp_path / "candidate-selection.json"

    adapter._motion(State.MOVE_ABOVE_OBJECT, target)

    assert len(planning_calls) == 4
    assert executed == [safe]
    candidates = [
        item
        for item in adapter._planning_attempts
        if item.get("kind") == "moveit_plan_candidate"
    ]
    assert [item["candidate_index"] for item in candidates] == [0, 1, 2, 3]
    assert candidates[0]["accepted"] is False
    assert candidates[1]["accepted"] is True
    assert adapter._planning_attempts[-1]["kind"] == "moveit_plan_selection"
    assert adapter._planning_attempts[-1]["candidate_index"] == 1


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


def test_only_moveit_control_failed_is_eligible_for_terminal_reconciliation() -> None:
    control_failed = ActionResult(
        ActionStatus.FAILED,
        Failure(
            FailureCategory.EXECUTION,
            "MOVEIT_EXECUTION_FAILED",
            "MoveIt execution error -6",
            {"moveit_error_code": -6.0},
        ),
    )
    planning_failed = ActionResult(
        ActionStatus.FAILED,
        Failure(
            FailureCategory.EXECUTION,
            "MOVEIT_EXECUTION_FAILED",
            "MoveIt execution error -1",
            {"moveit_error_code": -1.0},
        ),
    )

    assert RosDynamicMujocoExecution._is_reconcilable_control_failure(control_failed)
    assert not RosDynamicMujocoExecution._is_reconcilable_control_failure(planning_failed)
    assert not RosDynamicMujocoExecution._is_reconcilable_control_failure(
        ActionResult(ActionStatus.SUCCEEDED)
    )


def test_control_failure_terminal_pose_must_be_within_both_policy_tolerances() -> None:
    target = PoseEvidence((0.0200, -0.2800, 0.2000), (0.0, 0.0, 0.0, 1.0))
    within = PoseEvidence((0.0205, -0.2804, 0.2003), (0.0, 0.0, 0.01, 0.99995))
    outside = PoseEvidence((0.0230, -0.2800, 0.2000), (0.0, 0.0, 0.0, 1.0))

    accepted = RosDynamicMujocoExecution._terminal_pose_reconciliation(
        within,
        target,
        position_tolerance_m=0.002,
        orientation_tolerance_rad=0.10,
        orientation_error_rad=lambda _actual, _target: 0.02,
    )
    rejected = RosDynamicMujocoExecution._terminal_pose_reconciliation(
        outside,
        target,
        position_tolerance_m=0.002,
        orientation_tolerance_rad=0.10,
        orientation_error_rad=lambda _actual, _target: 0.02,
    )

    assert accepted == {
        "moveit_error_code": -6,
        "terminal_position_error_m": pytest.approx(math.dist(within.position_m, target.position_m)),
        "terminal_orientation_error_rad": pytest.approx(0.02),
    }
    assert rejected is None


def test_a_failed_release_marker_commit_ends_the_trace_in_error_with_the_failed_edge():
    """The Teacher manifest's `state_trace` must end in its `status` (ERROR): a commit failure used to stop the trace at the
    state whose action had succeeded, which the host could not verify (EXP-602)."""
    from so101_demo.core.runner import dry_run_actions
    from so101_demo.core.workflow import TEACHER_WORKFLOW

    class FailingObserver:
        def snapshot(self):
            raise RuntimeError("atomic evidence age 2.5s exceeds 0.2s")

    teacher_actions = {state: dry_run_actions()[state] for state in TEACHER_WORKFLOW.action_states}
    runner = StateMachineRunner(teacher_actions, session_id="s", world_observer=FailingObserver(),
                                workflow=TEACHER_WORKFLOW)

    result = runner.run(RunRequest(mode=RunMode.EXECUTE))

    assert result.status.value == "ERROR"
    assert result.failure.code == "RELEASE_MARKER_OBSERVATION_FAILED"
    assert result.current_state is State.ERROR
    assert result.state_trace[-2:] == (State.OPEN_GRIPPER, State.ERROR)
    assert result.transition_count == len(result.state_trace) - 1


def test_the_failure_boundary_event_of_a_failed_commit_names_its_failure():
    adapter = _finish_adapter()
    adapter._state_events.extend([{"state": "DETACH_MOVEIT"}, {"state": "OPEN_GRIPPER"}])

    adapter._annotate_boundary_event(State.OPEN_GRIPPER, "RELEASE_MARKER_OBSERVATION_FAILED")
    adapter._annotate_boundary_event(None, "ANY")
    adapter._annotate_boundary_event(State.LIFT, "ANY")

    assert adapter._state_events == [
        {"state": "DETACH_MOVEIT"},
        {"state": "OPEN_GRIPPER", "validation_failure": "RELEASE_MARKER_OBSERVATION_FAILED"},
    ]


def test_the_release_marker_is_observed_through_the_executions_waiting_snapshot():
    """One bare `observer.snapshot()` fails on a single stale sample; the execution's `_snapshot` spins and retries within its deadline."""
    from so101_demo.ros.dynamic_runtime import ExecutionSnapshotObserver

    sample = SimpleNamespace(simulation_session_id="s", publisher_sequence=7, reset_epoch=2)
    calls = []
    execution = SimpleNamespace(_snapshot=lambda: calls.append("snapshot") or sample)

    assert ExecutionSnapshotObserver(execution).snapshot() is sample
    assert calls == ["snapshot"]
