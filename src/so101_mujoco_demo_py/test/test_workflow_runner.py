import json
from dataclasses import dataclass

import pytest

from so101_mujoco_demo_py.domain import (
    ActionResult,
    ActionStatus,
    Failure,
    FailureCategory,
    RunMode,
    RunRequest,
    RunStatus,
    State,
)
from so101_mujoco_demo_py.runner import (
    CheckpointPhase,
    ExecutionContext,
    ExpectedWorldState,
    FileCheckpointStore,
    StateMachineRunner,
    WorkflowCheckpoint,
)
from so101_mujoco_demo_py.simulation.types import ObjectState, SimulationEvidence
from so101_mujoco_demo_py.workflow import SO101_WORKFLOW


@dataclass
class Action:
    state: State
    calls: int = 0

    def run(self, context: ExecutionContext) -> ActionResult:
        self.calls += 1
        if context.request.fail_at is self.state:
            return ActionResult(
                ActionStatus.FAILED,
                Failure(FailureCategory.INTERNAL, "INJECTED_FAILURE"),
            )
        return ActionResult(ActionStatus.SUCCEEDED)


class CheckpointSink:
    def __init__(self) -> None:
        self.values = []

    def commit(self, checkpoint):
        self.values.append(checkpoint)
        return None


def runner(checkpoint_store=None) -> tuple[StateMachineRunner, dict[State, Action]]:
    actions = {state: Action(state) for state in SO101_WORKFLOW.action_states}
    return StateMachineRunner(actions, checkpoint_store=checkpoint_store), actions


def world_evidence(
    *,
    sequence: int = 123,
    reset_epoch: int = 7,
    session_id: str = "session-a",
    position: tuple[float, float, float] = (0.0, -0.28, 0.165),
) -> SimulationEvidence:
    return SimulationEvidence(
        1.0,
        "world",
        sequence,
        10,
        reset_epoch,
        session_id,
        False,
        ObjectState(
            7,
            "plastic_cup",
            position,
            (0.0, 0.0, 0.0, 1.0),
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
        ),
        False,
        0.0,
        0.0,
        False,
        (),
        (),
        (),
    )


class Observer:
    def __init__(self, evidence: SimulationEvidence) -> None:
        self.evidence = evidence

    def snapshot(self) -> SimulationEvidence:
        return self.evidence


def test_full_dry_run_reaches_done_in_reference_order() -> None:
    machine, actions = runner()
    result = machine.run(RunRequest())
    assert result.status is RunStatus.DONE
    assert result.current_state is State.DONE
    assert result.transition_count == 19
    assert result.state_trace == (
        State.IDLE,
        State.PREPARE_OPEN_GRIPPER,
        State.MOVE_ABOVE_OBJECT,
        State.DESCEND,
        State.CLOSE_GRIPPER,
        State.WAIT_GRASP_STABLE,
        State.MICRO_LIFT,
        State.WAIT_MICRO_LIFT_STABLE,
        State.VERIFY_PHYSICAL_GRASP,
        State.ATTACH_MOVEIT,
        State.LIFT,
        State.MOVE_ABOVE_PLACE,
        State.DESCEND_TO_PLACE,
        State.DETACH_MOVEIT,
        State.OPEN_GRIPPER,
        State.WAIT_RELEASE_SETTLE,
        State.VALIDATE_FINAL_PLACEMENT,
        State.SYNC_WORLD_OBJECT,
        State.RETREAT,
        State.DONE,
    )
    assert all(
        action.calls == 1 for state, action in actions.items() if state in result.state_trace
    )


def test_stop_after_and_single_step_are_checkpoint_boundaries() -> None:
    stopped = runner()[0].run(RunRequest(stop_after=State.DESCEND))
    assert (stopped.status, stopped.current_state, stopped.next_state) == (
        RunStatus.CHECKPOINT_COMPLETE,
        State.DESCEND,
        State.CLOSE_GRIPPER,
    )
    stepped = runner()[0].run(RunRequest(single_step=True))
    assert (stepped.status, stepped.current_state, stepped.next_state) == (
        RunStatus.CHECKPOINT_COMPLETE,
        State.PREPARE_OPEN_GRIPPER,
        State.MOVE_ABOVE_OBJECT,
    )


def test_plan_only_rejects_unsupported_state_and_runs_one_supported_action() -> None:
    machine, actions = runner()
    bad = machine.run(RunRequest(mode=RunMode.PLAN_ONLY, plan_only_state=State.CLOSE_GRIPPER))
    assert bad.failure.code == "PLAN_ONLY_STATE_UNSUPPORTED"
    good = machine.run(RunRequest(mode=RunMode.PLAN_ONLY, plan_only_state=State.LIFT))
    assert good.status is RunStatus.PLAN_ONLY_COMPLETE
    assert actions[State.LIFT].calls == 1


def test_validation_failure_pauses_without_overwriting_physical_failure() -> None:
    result = runner()[0].run(RunRequest(fail_at=State.VERIFY_PHYSICAL_GRASP))
    assert result.status is RunStatus.CHECKPOINT_COMPLETE
    assert result.current_state is State.VALIDATION_FAILED
    assert result.next_state is State.ATTACH_MOVEIT
    assert result.failure.code == "INJECTED_FAILURE"


def test_transition_limit_and_force_continue_fail_closed() -> None:
    assert runner()[0].run(RunRequest(max_state_transitions=2)).failure.code == (
        "MAX_STATE_TRANSITIONS_EXCEEDED"
    )
    assert runner()[0].run(RunRequest(force_continue=True)).failure.code == (
        "FORCE_CONTINUE_NOT_ALLOWED"
    )


def test_post_release_checkpoint_is_non_resumable_and_has_fresh_epoch() -> None:
    sink = CheckpointSink()
    result = runner(sink)[0].run(RunRequest(stop_after=State.OPEN_GRIPPER))
    assert result.status is RunStatus.CHECKPOINT_COMPLETE
    checkpoint = sink.values[-1]
    assert checkpoint.resumable is False
    assert checkpoint.release_epoch_id
    assert checkpoint.release_marker_sequence == checkpoint.sequence


def test_file_checkpoint_round_trip_preserves_backend_neutral_transition(tmp_path) -> None:
    store = FileCheckpointStore(tmp_path / "checkpoint.json")
    result = runner(store)[0].run(RunRequest(stop_after=State.OPEN_GRIPPER))
    assert result.status is RunStatus.CHECKPOINT_COMPLETE
    checkpoint, failure = store.load()
    assert failure is None
    assert checkpoint.last_completed_state is State.OPEN_GRIPPER
    assert checkpoint.next_state is State.WAIT_RELEASE_SETTLE
    assert checkpoint.simulation_session_id == "dry-run"
    assert checkpoint.resumable is False
    assert checkpoint.expected.simulator_backend == "mujoco"
    assert checkpoint.expected.simulator_task_object_pose_world is None
    assert checkpoint.expected.simulator_task_object_constrained is False


def test_safe_v4_checkpoint_converts_to_v5_backend_neutral_fields(tmp_path) -> None:
    path = tmp_path / "checkpoint.json"
    path.write_text(
        """{
          "schema_version": 4,
          "run_id": "old-run",
          "sequence": 4,
          "source_mode": "dry_run",
          "phase": "FORWARD",
          "last_completed_state": "DESCEND",
          "failed_state": null,
          "original_failure": null,
          "next_state": "CLOSE_GRIPPER",
          "expected": {
            "tcp_pose_world": [0, 0, 0.2, 0, 0, 0, 1],
            "gripper_open": true,
            "joint_positions": {"1": 0.1},
            "moveit_world_object_poses": {},
            "moveit_task_object_attached": false,
            "gazebo_task_object_pose_world": [0, -0.28, 0.165, 0, 0, 0, 1],
            "gazebo_task_object_attached": false,
            "gazebo_task_object_stationary": true,
            "task_object_supported": true,
            "gripper_task_object_contact": false,
            "required_world_objects": ["plastic_cup"]
          },
          "policy_bundle_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          "simulation_session_id": "dry-run",
          "resumable": true,
          "release_epoch_id": null,
          "release_marker_sequence": null
        }""",
        encoding="utf-8",
    )
    checkpoint, failure = FileCheckpointStore(path).load()
    assert failure is None
    assert checkpoint.schema_version == 5
    assert checkpoint.expected == ExpectedWorldState(
        tcp_pose_world=(0.0, 0.0, 0.2, 0.0, 0.0, 0.0, 1.0),
        gripper_open=True,
        joint_positions={"1": 0.1},
        moveit_task_object_attached=False,
        simulator_task_object_pose_world=(0.0, -0.28, 0.165, 0.0, 0.0, 0.0, 1.0),
        simulator_task_object_constrained=False,
        simulator_task_object_stationary=True,
        task_object_supported=True,
        gripper_task_object_contact=False,
        required_world_objects=("plastic_cup",),
    )

    document = json.loads(path.read_text(encoding="utf-8"))
    document["expected"]["gazebo_task_object_attached"] = None
    path.write_text(json.dumps(document), encoding="utf-8")
    checkpoint, failure = FileCheckpointStore(path).load()
    assert failure is None
    assert checkpoint.expected.simulator_task_object_constrained is None
    resumed = runner(FileCheckpointStore(path))[0].run(
        RunRequest(resume=True, stop_after=State.CLOSE_GRIPPER)
    )
    assert resumed.status is RunStatus.ERROR
    assert resumed.failure.code == "RESUME_SIMULATOR_CONSTRAINT_UNKNOWN"


def test_v4_checkpoint_rejects_constraint_and_active_release_epoch(tmp_path) -> None:
    path = tmp_path / "checkpoint.json"
    store = FileCheckpointStore(path)
    baseline = {
        "schema_version": 4,
        "run_id": "old-run",
        "sequence": 4,
        "source_mode": "dry_run",
        "phase": "FORWARD",
        "last_completed_state": "DESCEND",
        "failed_state": None,
        "original_failure": None,
        "next_state": "CLOSE_GRIPPER",
        "expected": {
            "tcp_pose_world": [0, 0, 0.2, 0, 0, 0, 1],
            "gripper_open": True,
            "joint_positions": {},
            "moveit_world_object_poses": {},
            "moveit_task_object_attached": False,
            "gazebo_task_object_pose_world": None,
            "gazebo_task_object_attached": True,
            "gazebo_task_object_stationary": True,
            "task_object_supported": True,
            "gripper_task_object_contact": False,
            "required_world_objects": [],
        },
        "policy_bundle_sha256": "a" * 64,
        "simulation_session_id": "dry-run",
        "resumable": True,
        "release_epoch_id": None,
        "release_marker_sequence": None,
    }
    path.write_text(json.dumps(baseline), encoding="utf-8")
    assert store.load()[1].code == "CHECKPOINT_INCOMPATIBLE"
    baseline["expected"]["gazebo_task_object_attached"] = False
    baseline["release_epoch_id"] = "release-1"
    baseline["release_marker_sequence"] = 4
    baseline["resumable"] = False
    path.write_text(json.dumps(baseline), encoding="utf-8")
    checkpoint, failure = store.load()
    assert failure is None
    assert checkpoint.resumable is False
    assert checkpoint.release_epoch_id == "release-1"


def test_resume_starts_from_checkpoint_next_state_and_validates_session(tmp_path) -> None:
    store = FileCheckpointStore(tmp_path / "checkpoint.json")
    checkpoint = WorkflowCheckpoint(
        run_id="run-1",
        sequence=4,
        source_mode=RunMode.DRY_RUN,
        phase=CheckpointPhase.FORWARD,
        last_completed_state=State.DESCEND,
        failed_state=None,
        original_failure=None,
        next_state=State.CLOSE_GRIPPER,
        expected=ExpectedWorldState(),
        policy_bundle_sha256="a" * 64,
        simulation_session_id="session-a",
        resumable=True,
    )
    assert store.commit(checkpoint) is None
    machine, actions = runner(store)
    machine.session_id = "session-a"
    result = machine.run(RunRequest(resume=True, stop_after=State.CLOSE_GRIPPER))
    assert result.status is RunStatus.CHECKPOINT_COMPLETE
    assert result.state_trace == (State.DESCEND, State.CLOSE_GRIPPER)
    assert actions[State.PREPARE_OPEN_GRIPPER].calls == 0
    assert actions[State.CLOSE_GRIPPER].calls == 1

    machine.session_id = "session-b"
    mismatch = machine.run(RunRequest(resume=True))
    assert mismatch.failure.code == "RESUME_SESSION_MISMATCH"


def test_live_resume_compares_checkpoint_expected_pose_to_task5_evidence(tmp_path) -> None:
    store = FileCheckpointStore(tmp_path / "checkpoint.json")
    checkpoint = WorkflowCheckpoint(
        run_id="run-1",
        sequence=4,
        source_mode=RunMode.EXECUTE,
        phase=CheckpointPhase.FORWARD,
        last_completed_state=State.DESCEND,
        failed_state=None,
        original_failure=None,
        next_state=State.CLOSE_GRIPPER,
        expected=ExpectedWorldState(
            simulator_task_object_pose_world=(
                0.0,
                -0.28,
                0.165,
                0.0,
                0.0,
                0.0,
                1.0,
            )
        ),
        policy_bundle_sha256="a" * 64,
        simulation_session_id="session-a",
        resumable=True,
    )
    assert store.commit(checkpoint) is None
    machine, _ = runner(store)
    machine.session_id = "session-a"
    machine.world_observer = Observer(world_evidence(position=(0.02, -0.28, 0.165)))
    machine.observed_world_provider = lambda: ExpectedWorldState()
    mismatch = machine.run(RunRequest(mode=RunMode.EXECUTE, resume=True))
    assert mismatch.failure.code == "RESUME_WORLD_MISMATCH"


@pytest.mark.parametrize(
    ("change", "value"),
    (
        ("tcp_pose_world", (0.2, 0.0, 0.3, 0.0, 0.0, 0.0, 1.0)),
        ("gripper_open", False),
        ("joint_positions", {"1": 0.1, "2": 9.0}),
        (
            "moveit_world_object_poses",
            {"plastic_cup": (0.5, -0.28, 0.165, 0.0, 0.0, 0.0, 1.0)},
        ),
        ("moveit_task_object_attached", True),
        ("task_object_supported", False),
        ("required_world_object_membership", None),
    ),
)
def test_execute_resume_rejects_each_contradictory_world_fact(
    tmp_path, change: str, value: object
) -> None:
    store = FileCheckpointStore(tmp_path / "checkpoint.json")
    expected = ExpectedWorldState(
        tcp_pose_world=(0.1, 0.0, 0.3, 0.0, 0.0, 0.0, 1.0),
        gripper_open=True,
        joint_positions={"1": 0.1, "2": 0.2},
        moveit_world_object_poses={"plastic_cup": (0.0, -0.28, 0.165, 0.0, 0.0, 0.0, 1.0)},
        moveit_task_object_attached=False,
        simulator_task_object_pose_world=(
            0.0,
            -0.28,
            0.165,
            0.0,
            0.0,
            0.0,
            1.0,
        ),
        simulator_task_object_stationary=True,
        task_object_supported=True,
        gripper_task_object_contact=False,
        required_world_objects=("plastic_cup", "table", "pedestal"),
    )
    checkpoint = WorkflowCheckpoint(
        run_id="run-1",
        sequence=4,
        source_mode=RunMode.EXECUTE,
        phase=CheckpointPhase.FORWARD,
        last_completed_state=State.DESCEND,
        failed_state=None,
        original_failure=None,
        next_state=State.CLOSE_GRIPPER,
        expected=expected,
        policy_bundle_sha256="a" * 64,
        simulation_session_id="session-a",
        resumable=True,
    )
    assert store.commit(checkpoint) is None
    observed_values = {
        "tcp_pose_world": (0.1, 0.0, 0.3, 0.0, 0.0, 0.0, 1.0),
        "gripper_open": True,
        "joint_positions": {"1": 0.1, "2": 0.2},
        "moveit_world_object_poses": {
            "plastic_cup": (0.0, -0.28, 0.165, 0.0, 0.0, 0.0, 1.0),
            "table": (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0),
            "pedestal": (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0),
        },
        "moveit_task_object_attached": False,
        "task_object_supported": True,
        "required_world_objects": ("plastic_cup", "table", "pedestal"),
    }
    if change == "required_world_object_membership":
        observed_values["moveit_world_object_poses"].pop("pedestal")
    else:
        observed_values[change] = value
    observed = ExpectedWorldState(**observed_values)
    machine, _ = runner(store)
    machine.session_id = "session-a"
    machine.world_observer = Observer(world_evidence())
    machine.observed_world_provider = lambda: observed
    mismatch = machine.run(RunRequest(mode=RunMode.EXECUTE, resume=True))
    assert mismatch.failure.code == "RESUME_WORLD_MISMATCH"


def test_execute_resume_requires_and_accepts_complete_current_world_observation(tmp_path) -> None:
    store = FileCheckpointStore(tmp_path / "checkpoint.json")
    expected = ExpectedWorldState(
        tcp_pose_world=(0.1, 0.0, 0.3, 0.0, 0.0, 0.0, 1.0),
        gripper_open=True,
        joint_positions={"1": 0.1},
        moveit_world_object_poses={"plastic_cup": (0.0, -0.28, 0.165, 0.0, 0.0, 0.0, 1.0)},
        moveit_task_object_attached=False,
        simulator_task_object_pose_world=(0.0, -0.28, 0.165, 0.0, 0.0, 0.0, 1.0),
        task_object_supported=True,
        required_world_objects=("plastic_cup", "table"),
    )
    checkpoint = WorkflowCheckpoint(
        run_id="run-1",
        sequence=4,
        source_mode=RunMode.EXECUTE,
        phase=CheckpointPhase.FORWARD,
        last_completed_state=State.DESCEND,
        failed_state=None,
        original_failure=None,
        next_state=State.CLOSE_GRIPPER,
        expected=expected,
        policy_bundle_sha256="a" * 64,
        simulation_session_id="session-a",
        resumable=True,
    )
    assert store.commit(checkpoint) is None
    machine, _ = runner(store)
    machine.session_id = "session-a"
    machine.world_observer = Observer(world_evidence())
    missing = machine.run(RunRequest(mode=RunMode.EXECUTE, resume=True))
    assert missing.failure.code == "RESUME_OBSERVATION_REQUIRED"

    observed = ExpectedWorldState(
        tcp_pose_world=expected.tcp_pose_world,
        gripper_open=expected.gripper_open,
        joint_positions=expected.joint_positions,
        moveit_world_object_poses={
            **expected.moveit_world_object_poses,
            "table": (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0),
        },
        moveit_task_object_attached=expected.moveit_task_object_attached,
        task_object_supported=expected.task_object_supported,
    )
    machine.observed_world_provider = lambda: observed
    machine.expected_world_provider = lambda _context: expected
    resumed = machine.run(
        RunRequest(mode=RunMode.EXECUTE, resume=True, stop_after=State.CLOSE_GRIPPER)
    )
    assert resumed.status is RunStatus.CHECKPOINT_COMPLETE


def test_execute_checkpoint_uses_injected_expected_world_provider(tmp_path) -> None:
    store = FileCheckpointStore(tmp_path / "checkpoint.json")
    machine, _ = runner(store)
    machine.session_id = "session-a"
    machine.expected_world_provider = lambda _context: ExpectedWorldState(
        simulator_task_object_pose_world=(
            0.0,
            -0.28,
            0.165,
            0.0,
            0.0,
            0.0,
            1.0,
        ),
        simulator_task_object_stationary=True,
        gripper_task_object_contact=False,
    )
    result = machine.run(RunRequest(mode=RunMode.EXECUTE, stop_after=State.PREPARE_OPEN_GRIPPER))
    assert result.status is RunStatus.CHECKPOINT_COMPLETE
    checkpoint, failure = store.load()
    assert failure is None
    assert checkpoint.expected.simulator_task_object_pose_world == (
        0.0,
        -0.28,
        0.165,
        0.0,
        0.0,
        0.0,
        1.0,
    )

    resumed, _ = runner(store)
    resumed.session_id = "session-a"
    resumed.world_observer = Observer(world_evidence(position=(99.0, 99.0, 99.0)))
    resumed.observed_world_provider = lambda: ExpectedWorldState()
    mismatch = resumed.run(RunRequest(mode=RunMode.EXECUTE, resume=True))
    assert mismatch.failure.code == "RESUME_WORLD_MISMATCH"


def test_release_marker_uses_task5_publisher_sequence_and_reset_epoch() -> None:
    sink = CheckpointSink()
    machine, _ = runner(sink)
    machine.session_id = "session-a"
    machine.world_observer = Observer(world_evidence(sequence=456, reset_epoch=9))
    result = machine.run(RunRequest(stop_after=State.OPEN_GRIPPER))
    assert result.status is RunStatus.CHECKPOINT_COMPLETE
    checkpoint = sink.values[-1]
    assert checkpoint.release_marker_sequence == 456
    assert machine.release_reset_epoch == 9
