"""Deterministic ROS-free state-machine runner."""

from dataclasses import dataclass
from typing import Mapping, Protocol
import uuid

from .checkpoint import Checkpoint, CheckpointPhase, ExpectedWorldState, FileCheckpointStore
from .domain import (
    ActionResult, ActionStatus, Failure, FailureCategory, RunMode, RunRequest,
    RunResult, RunStatus, State,
)
from .workflow import SO101_WORKFLOW, resolve_transition


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    request: RunRequest
    state: State
    transition_count: int


class StateAction(Protocol):
    def run(self, context: ExecutionContext) -> ActionResult: ...


class StateMachineRunner:
    def __init__(
        self,
        actions: Mapping[State, StateAction],
        checkpoint_store: FileCheckpointStore | None = None,
        session_id: str = "",
        policy_bundle_sha256: str = "",
    ) -> None:
        self.actions = dict(actions)
        self.checkpoint_store = checkpoint_store
        self.session_id = session_id
        self.policy_bundle_sha256 = policy_bundle_sha256
        self.release_epoch_id: str | None = None
        self.release_marker_sequence: int | None = None

    def _error(
        self, code: str, trace: list[State], count: int,
        category: FailureCategory = FailureCategory.INTERNAL,
    ) -> RunResult:
        return RunResult(
            RunStatus.ERROR, trace[-1], None, Failure(category, code), count, tuple(trace)
        )

    def _commit(
        self, request: RunRequest, completed: State, next_state: State,
        count: int, failure: Failure | None,
    ) -> Failure | None:
        if self.checkpoint_store is None:
            return None
        if completed is State.OPEN_GRIPPER and self.release_epoch_id is None:
            self.release_epoch_id = str(uuid.uuid4())
            self.release_marker_sequence = count
        release_active = completed in {
            State.OPEN_GRIPPER, State.WAIT_RELEASE_SETTLE,
            State.VALIDATE_FINAL_PLACEMENT,
        }
        checkpoint = Checkpoint(
            run_id=str(uuid.uuid4()), sequence=count, source_mode=request.mode,
            phase=CheckpointPhase.RECOVERY if completed.name.startswith("RECOVER_") else CheckpointPhase.FORWARD,
            last_completed_state=completed, failed_state=completed if failure else None,
            original_failure=failure, next_state=next_state,
            expected=ExpectedWorldState(),
            policy_bundle_sha256=self.policy_bundle_sha256 or "unconfigured",
            simulation_session_id=self.session_id or "dry-run", resumable=not release_active,
            release_epoch_id=self.release_epoch_id if release_active else None,
            release_marker_sequence=self.release_marker_sequence if release_active else None,
        )
        return self.checkpoint_store.commit(checkpoint)

    def run(self, request: RunRequest) -> RunResult:
        if request.force_continue:
            return self._error("FORCE_CONTINUE_NOT_ALLOWED", [State.IDLE], 0, FailureCategory.RESUME_VALIDATION)
        if request.mode is RunMode.PLAN_ONLY:
            state = request.plan_only_state
            if state not in SO101_WORKFLOW.plan_only_states:
                return self._error("PLAN_ONLY_STATE_UNSUPPORTED", [State.IDLE], 0, FailureCategory.CONFIGURATION)
            action = self.actions.get(state)
            if action is None:
                return self._error("ACTION_NOT_REGISTERED", [state], 0)
            result = action.run(ExecutionContext(request, state, 0))
            if result.status is not ActionStatus.SUCCEEDED:
                return RunResult(RunStatus.ERROR, state, None, result.failure, 1, (state,))
            return RunResult(RunStatus.PLAN_ONLY_COMPLETE, state, None, None, 1, (state,))

        trace = [State.IDLE, State.PREPARE_OPEN_GRIPPER]
        current = State.PREPARE_OPEN_GRIPPER
        # R3 counts the initial IDLE -> PREPARE_OPEN_GRIPPER transition.
        count = 1
        original_failure: Failure | None = None
        while current not in SO101_WORKFLOW.terminal_states:
            if count >= request.max_state_transitions:
                return self._error("MAX_STATE_TRANSITIONS_EXCEEDED", trace, count)
            action = self.actions.get(current)
            if action is None:
                return self._error("ACTION_NOT_REGISTERED", trace, count)
            action_result = action.run(ExecutionContext(request, current, count))
            count += 1
            if action_result.status is not ActionStatus.SUCCEEDED and original_failure is None:
                original_failure = action_result.failure or Failure(FailureCategory.INTERNAL, "ACTION_FAILED")
            next_state = resolve_transition(current, action_result.status)
            commit_failure = self._commit(request, current, next_state, count, original_failure)
            if commit_failure is not None:
                return RunResult(RunStatus.ERROR, current, None, commit_failure, count, tuple(trace))
            if next_state is State.VALIDATION_FAILED:
                trace.append(State.VALIDATION_FAILED)
                return RunResult(
                    RunStatus.CHECKPOINT_COMPLETE, State.VALIDATION_FAILED,
                    State.ATTACH_MOVEIT, original_failure, count, tuple(trace),
                )
            if request.stop_after is current or request.single_step:
                return RunResult(
                    RunStatus.CHECKPOINT_COMPLETE, current, next_state,
                    original_failure, count, tuple(trace),
                )
            current = next_state
            trace.append(current)
        if current is State.DONE:
            return RunResult(RunStatus.DONE, current, None, None, count, tuple(trace))
        return RunResult(RunStatus.ERROR, current, None, original_failure, count, tuple(trace))


@dataclass(slots=True)
class SuccessfulAction:
    def run(self, context: ExecutionContext) -> ActionResult:
        if context.request.fail_at is context.state:
            return ActionResult(
                ActionStatus.FAILED,
                Failure(FailureCategory.INTERNAL, "INJECTED_FAILURE", "failure injected by request"),
            )
        return ActionResult(ActionStatus.SUCCEEDED)


def dry_run_actions() -> dict[State, StateAction]:
    return {state: SuccessfulAction() for state in SO101_WORKFLOW.action_states}
