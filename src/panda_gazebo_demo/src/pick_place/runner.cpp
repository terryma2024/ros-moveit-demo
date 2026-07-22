#include "panda_gazebo_demo/pick_place/runner.hpp"

#include <chrono>
#include <thread>
#include <utility>

namespace panda_gazebo_demo::pick_place
{

namespace
{

constexpr auto kStationaryTimeout = std::chrono::seconds(2);
constexpr auto kStationaryPollInterval = std::chrono::milliseconds(25);

WorldSnapshot snapshotFromExpected(
  const ExpectedWorldState & expected,
  const std::string & simulation_session_id)
{
  WorldSnapshot snapshot;
  snapshot.observed_at = std::chrono::steady_clock::now();
  snapshot.fresh = true;
  snapshot.arm_stationary = true;
  snapshot.gripper_open = expected.gripper_open;
  snapshot.tcp_pose_world = expected.tcp_pose_world;
  snapshot.joint_positions = expected.joint_positions;
  snapshot.moveit_world_object_poses = expected.moveit_world_object_poses;
  snapshot.moveit_coke_attached = expected.moveit_coke_attached;
  snapshot.gazebo_coke_pose_world = expected.gazebo_coke_pose_world;
  snapshot.gazebo_coke_attached = expected.gazebo_coke_attached;
  snapshot.gazebo_coke_stationary = expected.gazebo_coke_stationary;
  snapshot.simulation_session_id = simulation_session_id;
  return snapshot;
}

void setExpectedWorldState(Checkpoint & checkpoint, const WorldSnapshot & snapshot)
{
  checkpoint.expected.tcp_pose_world = snapshot.tcp_pose_world;
  checkpoint.expected.gripper_open = snapshot.gripper_open;
  checkpoint.expected.joint_positions = snapshot.joint_positions;
  checkpoint.expected.moveit_world_object_poses = snapshot.moveit_world_object_poses;
  checkpoint.expected.moveit_coke_attached = snapshot.moveit_coke_attached;
  checkpoint.expected.gazebo_coke_pose_world = snapshot.gazebo_coke_pose_world;
  checkpoint.expected.gazebo_coke_attached = snapshot.gazebo_coke_attached;
  checkpoint.expected.gazebo_coke_stationary = snapshot.gazebo_coke_stationary;
  for (const auto & [object_id, pose] : snapshot.moveit_world_object_poses) {
    static_cast<void>(pose);
    checkpoint.expected.required_world_objects.push_back(object_id);
  }
}

Failure withOriginalFailure(Failure recovery_failure, const Failure & original_failure)
{
  recovery_failure.message += " | original failure " + original_failure.code + ": " +
    original_failure.message;
  for (const auto & [name, value] : original_failure.metrics) {
    recovery_failure.metrics["original_" + name] = value;
  }
  return recovery_failure;
}

}  // namespace

RunResult StateMachineRunner::run(const RunRequest & request) const
{
  if (request.max_state_transitions == 0) {
    return error(State::IDLE, {FailureCategory::CONFIGURATION, "INVALID_MAX_TRANSITIONS",
               "max_state_transitions must be greater than zero", {}});
  }
  if (request.fail_at.has_value() && request.mode != RunMode::DRY_RUN) {
    return error(State::IDLE, {FailureCategory::CONFIGURATION, "FAIL_AT_MODE_MISMATCH",
               "fail_at is supported only in dry_run mode", {}});
  }
  if (request.resume) {
    return runResume(request);
  }
  switch (request.mode) {
    case RunMode::DRY_RUN:
      return runDryRun(request);
    case RunMode::PLAN_ONLY:
      return runPlanOnly(request);
    case RunMode::EXECUTE: {
        const TransitionTable transitions;
        return runExecuteWorkflow(
          transitions.resolve(State::IDLE, ActionStatus::SUCCEEDED), request, std::nullopt, 1, 1);
      }
  }
  return error(State::IDLE, {FailureCategory::INTERNAL, "UNKNOWN_MODE", "Unknown run mode", {}});
}

RunResult StateMachineRunner::runDryRun(const RunRequest & request) const
{
  StateMachine state_machine;
  std::uint64_t transition_count = 0;
  std::optional<Failure> injected_failure;
  while (!state_machine.isTerminal() && transition_count < request.max_state_transitions) {
    const auto current = state_machine.currentState();
    const auto status = request.fail_at == current ? ActionStatus::FAILED : ActionStatus::SUCCEEDED;
    const auto next = state_machine.advance(status);
    ++transition_count;
    if (status != ActionStatus::SUCCEEDED) {
      injected_failure = Failure{FailureCategory::INTERNAL, "DRY_RUN_FAILURE_INJECTED",
        std::string("dry_run failure injected at ") + toString(current), {}};
    }
    if (status == ActionStatus::SUCCEEDED && request.stop_after == current) {
      return {RunStatus::CHECKPOINT_COMPLETE, next, next, std::nullopt, transition_count};
    }
  }
  if (!state_machine.isTerminal()) {
    return error(state_machine.currentState(),
             {FailureCategory::INTERNAL, "MAX_TRANSITIONS_EXCEEDED",
               "State machine exceeded max_state_transitions", {}}, transition_count);
  }
  return {state_machine.currentState() == State::DONE ? RunStatus::DONE : RunStatus::ERROR,
    state_machine.currentState(), std::nullopt, injected_failure, transition_count};
}

RunResult StateMachineRunner::runPlanOnly(const RunRequest & request) const
{
  return runPlanOnly(State::MOVE_ABOVE_OBJECT, request);
}

RunResult StateMachineRunner::runPlanOnly(
  State state, const RunRequest & request,
  std::optional<ObservationResult> observation) const
{
  if (request.stop_after.has_value()) {
    return error(state, {FailureCategory::CONFIGURATION, "STOP_AFTER_PLAN_ONLY_UNSUPPORTED",
               "plan_only does not execute actions or create checkpoints", {}});
  }
  auto * planner = actions_.findPlanner(state);
  if (planner == nullptr) {
    return error(state, {FailureCategory::PLANNING, "PLANNER_NOT_REGISTERED",
               std::string("No planner is registered for ") + toString(state), {}});
  }
  if (plan_validators_ == nullptr || !plan_validators_->hasValidator(state)) {
    return error(state, {FailureCategory::CONFIGURATION, "PLAN_VALIDATOR_NOT_REGISTERED",
               std::string("No plan validator is registered for ") + toString(state), {}});
  }
  if (!observation) {
    if (observer_ == nullptr) {
      return error(state, {FailureCategory::CONFIGURATION, "TARGET_OBSERVER_MISSING",
                 "plan_only requires an observer for target policy input", {}});
    }
    observation = observer_->observe();
  }
  if (!observation->snapshot) {
    return error(state, observation->failure.value_or(Failure{
        FailureCategory::OBSERVATION, "TARGET_OBSERVATION_FAILED",
        "Could not observe the world before planning", {}}));
  }
  const TransitionTable transitions;
  const auto next_state = transitions.resolve(state, ActionStatus::SUCCEEDED);
  const auto plan = planner->plan(state, next_state, *observation);
  if (plan.action.status != ActionStatus::SUCCEEDED || !plan.artifact) {
    return error(state, plan.action.failure.value_or(Failure{
        FailureCategory::PLAN_VALIDATION, "EMPTY_PLAN_ARTIFACT",
        "Planner returned no usable trajectory", {}}));
  }
  const auto plan_validation = plan_validators_->validate(state, *observation->snapshot,
      *plan.artifact);
  if (!plan_validation.ok) {
    return error(state, plan_validation.failures.front());
  }
  return {RunStatus::PLAN_ONLY_COMPLETE, state,
    next_state, std::nullopt, 0};
}

RunResult StateMachineRunner::runExecuteWorkflow(
  State initial_state, const RunRequest & request, std::optional<WorldSnapshot> initial_snapshot,
  std::uint64_t checkpoint_sequence, std::uint64_t initial_transition_count,
  CheckpointPhase phase, std::optional<State> failed_state,
  std::optional<Failure> original_failure) const
{
  State state = initial_state;
  std::uint64_t transition_count = initial_transition_count;
  std::optional<Failure> workflow_failure = std::move(original_failure);
  while (!isTerminal(state) && transition_count < request.max_state_transitions) {
    const auto step = runExecuteStep(
      state, initial_snapshot, checkpoint_sequence, phase, failed_state, workflow_failure);
    initial_snapshot.reset();
    ++transition_count;
    if (step.status == RunStatus::ERROR) {
      auto failed = step;
      if (phase == CheckpointPhase::RECOVERY && workflow_failure && step.failure) {
        failed.failure = withOriginalFailure(*step.failure, *workflow_failure);
      }
      failed.transition_count = transition_count;
      return failed;
    }
    if (!step.next_state) {
      return error(state, {FailureCategory::INTERNAL, "WORKFLOW_NEXT_STATE_MISSING",
                 "Successful execute step did not provide its next state", {}}, transition_count);
    }
    if (step.status == RunStatus::CHECKPOINT_COMPLETE && request.stop_after == state) {
      auto stopped = step;
      stopped.transition_count = transition_count;
      return stopped;
    }
    if (phase == CheckpointPhase::FORWARD && step.status == RunStatus::RUNNING && step.failure &&
      !isForwardAction(*step.next_state))
    {
      phase = CheckpointPhase::RECOVERY;
      failed_state = state;
      workflow_failure = step.failure;
      ++checkpoint_sequence;
    }
    state = *step.next_state;
    if (step.status == RunStatus::CHECKPOINT_COMPLETE) {
      ++checkpoint_sequence;
    }
  }
  if (!isTerminal(state)) {
    return error(state, {FailureCategory::INTERNAL, "MAX_TRANSITIONS_EXCEEDED",
               "State machine exceeded max_state_transitions", {}}, transition_count);
  }
  if (state == State::DONE) {
    return {RunStatus::DONE, state, std::nullopt, std::nullopt, transition_count};
  }
  return {RunStatus::ERROR, State::ERROR, std::nullopt,
    workflow_failure.value_or(Failure{FailureCategory::INTERNAL, "WORKFLOW_REACHED_ERROR",
        "Workflow reached ERROR without a recorded failure", {}}), transition_count};
}

RunResult StateMachineRunner::runExecuteStep(
  State state, std::optional<WorldSnapshot> before,
  std::uint64_t checkpoint_sequence, CheckpointPhase phase,
  std::optional<State> failed_state, std::optional<Failure> original_failure) const
{
  const TransitionTable transitions;
  const auto next_state = transitions.resolve(state, ActionStatus::SUCCEEDED);
  if (observer_ == nullptr || checkpoint_store_ == nullptr) {
    return error(state, {FailureCategory::CONFIGURATION,
               "EXECUTE_INFRASTRUCTURE_MISSING",
               "execute requires a world observer and checkpoint store", {}});
  }
  if (common_resume_validator_ == nullptr) {
    return error(state, {FailureCategory::CONFIGURATION,
               "COMMON_RESUME_VALIDATOR_MISSING",
               "execute requires a CommonResumeValidator to bind checkpoints to configuration",
               {}});
  }
  if (phase == CheckpointPhase::RECOVERY && (!failed_state || !original_failure)) {
    return error(state, {FailureCategory::CONFIGURATION,
               "RECOVERY_EXECUTION_CONTEXT_INCOMPLETE",
               "Recovery execution requires the failed state and original failure", {}});
  }
  auto * executor = actions_.findExecutor(state);
  if (executor == nullptr) {
    return error(state, {FailureCategory::CONFIGURATION,
               "EXECUTE_ACTION_NOT_REGISTERED",
               std::string("State requires an executor: ") + toString(state), {}});
  }
  if (!contracts_.hasContract({state, next_state})) {
    return error(state, {FailureCategory::CONFIGURATION,
               "MISSING_TRANSITION_CONTRACT",
               std::string("Missing execute contract for ") + toString(state) + " -> " +
               toString(next_state), {}});
  }
  if (!before) {
    const auto observation = observer_->observe();
    if (!observation.snapshot) {
      return error(state, observation.failure.value_or(Failure{
          FailureCategory::OBSERVATION, "PRE_EXECUTION_OBSERVATION_FAILED",
          "Could not observe the world before execution", {}}));
    }
    before = *observation.snapshot;
  }
  const ObservationResult planning_observation{*before, std::nullopt};
  const auto precondition = contracts_.validatePrecondition({state, next_state}, *before);
  if (!precondition.ok) {
    return error(state, precondition.failures.front());
  }
  std::shared_ptr<const PlanArtifact> plan_artifact;
  if (auto * planner = actions_.findPlanner(state)) {
    if (plan_validators_ == nullptr || !plan_validators_->hasValidator(state)) {
      return error(state, {FailureCategory::CONFIGURATION,
                 "PLAN_VALIDATOR_NOT_REGISTERED",
                 std::string("No plan validator is registered for ") + toString(state), {}});
    }
    const auto plan = planner->plan(state, next_state, planning_observation);
    if (plan.action.status != ActionStatus::SUCCEEDED || !plan.artifact) {
      return error(state, plan.action.failure.value_or(Failure{
          FailureCategory::PLAN_VALIDATION, "EMPTY_PLAN_ARTIFACT",
          "Planner returned no usable trajectory", {}}));
    }
    const auto plan_validation = plan_validators_->validate(state, *before, *plan.artifact);
    if (!plan_validation.ok) {
      return error(state, plan_validation.failures.front());
    }
    plan_artifact = plan.artifact;
  }
  const auto action = executor->execute({state, next_state, *before, plan_artifact});
  if (action.status != ActionStatus::SUCCEEDED) {
    return handleActionFailure(state, *executor,
      action.failure.value_or(Failure{FailureCategory::EXECUTION, "EXECUTION_FAILED",
               "Trajectory execution failed", {}}), checkpoint_sequence);
  }
  const auto after = observer_->observe();
  if (!after.snapshot) {
    const auto observation_failure = after.failure.value_or(Failure{
        FailureCategory::OBSERVATION, "POST_EXECUTION_OBSERVATION_FAILED",
        "Could not observe the world after execution", {}});
    return handleActionFailure(state, *executor, observation_failure, checkpoint_sequence);
  }
  if (execution_observation_sink_ != nullptr) {
    execution_observation_sink_->record(state, *before, *after.snapshot);
  }
  const auto validation = contracts_.validate({state, next_state}, *before, *after.snapshot,
      action);
  if (!validation.ok) {
    return handleActionFailure(
      state, *executor, validation.failures.front(), checkpoint_sequence);
  }
  Checkpoint checkpoint;
  checkpoint.run_id = "pick_place_state_machine";
  checkpoint.sequence = checkpoint_sequence;
  checkpoint.phase = phase;
  checkpoint.last_completed_state = state;
  checkpoint.failed_state = failed_state;
  checkpoint.original_failure = original_failure;
  checkpoint.next_state = next_state;
  setExpectedWorldState(checkpoint, *after.snapshot);
  checkpoint.simulation_session_id = common_resume_validator_->simulationSessionId();
  checkpoint.configuration_hash = common_resume_validator_->configurationHash();
  if (const auto checkpoint_failure = checkpoint_store_->commit(checkpoint)) {
    return error(state, *checkpoint_failure);
  }
  return {RunStatus::CHECKPOINT_COMPLETE, state, next_state, std::nullopt, 1};
}

RunResult StateMachineRunner::runResume(const RunRequest & request) const
{
  if (request.mode == RunMode::DRY_RUN) {
    return error(State::IDLE, {FailureCategory::CONFIGURATION, "RESUME_DRY_RUN_UNSUPPORTED",
               "resume is supported only in plan_only and execute modes", {}});
  }
  if (observer_ == nullptr || checkpoint_store_ == nullptr) {
    return error(State::IDLE, {FailureCategory::RESUME_VALIDATION, "RESUME_INFRASTRUCTURE_MISSING",
               "resume requires a world observer and checkpoint store", {}});
  }
  const auto loaded = checkpoint_store_->loadLatestCompatible();
  if (!loaded.checkpoint) {
    return error(State::IDLE, loaded.failure.value_or(Failure{
        FailureCategory::CHECKPOINT, "CHECKPOINT_LOAD_FAILED", "Unable to load checkpoint", {}}));
  }
  const auto & checkpoint = *loaded.checkpoint;
  const TransitionTable transitions;
  const bool invalid_forward_transition = checkpoint.phase == CheckpointPhase::FORWARD &&
    (isTerminal(checkpoint.last_completed_state) ||
    transitions.resolve(checkpoint.last_completed_state, ActionStatus::SUCCEEDED) !=
    checkpoint.next_state);
  const bool invalid_recovery_context = checkpoint.phase == CheckpointPhase::RECOVERY &&
    (!checkpoint.failed_state || !checkpoint.original_failure);
  if (checkpoint.schema_version != 3 || checkpoint.source_mode != RunMode::EXECUTE ||
    !checkpoint.resumable || invalid_forward_transition || invalid_recovery_context)
  {
    return error(State::IDLE, {FailureCategory::RESUME_VALIDATION, "CHECKPOINT_INCOMPATIBLE",
               "Checkpoint does not describe a valid successful workflow transition", {}});
  }
  const auto observation = observer_->observe();
  if (!observation.snapshot) {
    return error(checkpoint.next_state, observation.failure.value_or(Failure{
        FailureCategory::RESUME_VALIDATION, "RESUME_OBSERVATION_FAILED",
        "Unable to observe the world while resuming", {}}));
  }
  if (common_resume_validator_ == nullptr) {
    return error(checkpoint.next_state, {FailureCategory::RESUME_VALIDATION,
               "COMMON_RESUME_VALIDATOR_MISSING", "resume requires a CommonResumeValidator", {}});
  }
  const auto & snapshot = *observation.snapshot;
  const auto common_validation = common_resume_validator_->validate(checkpoint, snapshot);
  if (!common_validation.ok) {
    return error(checkpoint.next_state, common_validation.failures.front());
  }
  if (checkpoint.phase == CheckpointPhase::RECOVERY) {
    if (recovery_policy_ == nullptr) {
      return error(checkpoint.next_state, {FailureCategory::CONFIGURATION,
                 "RECOVERY_POLICY_MISSING",
                 "Recovery resume requires an IRecoveryPolicy", {}});
    }
    const auto route = recovery_policy_->select(
      *checkpoint.failed_state, *checkpoint.original_failure, snapshot);
    if (!route.next_state) {
      auto route_failure = route.failure.value_or(Failure{FailureCategory::INTERNAL,
            "RECOVERY_ROUTE_MISSING", "Recovery policy did not select a safe route during resume",
            {}});
      return error(checkpoint.next_state,
        withOriginalFailure(std::move(route_failure), *checkpoint.original_failure));
    }
    if (isForwardAction(*route.next_state) || isTerminal(*route.next_state)) {
      return error(checkpoint.next_state, {FailureCategory::CONFIGURATION,
                 "RECOVERY_ROUTE_INVALID",
                 "Recovery policy selected a forward or terminal state during resume", {}});
    }
    if (request.mode == RunMode::PLAN_ONLY) {
      return runPlanOnly(*route.next_state, request, ObservationResult{snapshot, std::nullopt});
    }
    return runExecuteWorkflow(
      *route.next_state, request, snapshot, checkpoint.sequence + 1, 0,
      CheckpointPhase::RECOVERY, checkpoint.failed_state, checkpoint.original_failure);
  }
  const TransitionKey resumed_transition{
    checkpoint.last_completed_state, checkpoint.next_state};
  if (!contracts_.hasContract(resumed_transition)) {
    return error(checkpoint.next_state, {FailureCategory::CONFIGURATION,
               "MISSING_TRANSITION_CONTRACT", "resume requires a transition validator", {}});
  }
  const auto transition_validation = contracts_.validateResume(
    resumed_transition, snapshotFromExpected(checkpoint.expected, checkpoint.simulation_session_id),
    snapshot);
  if (!transition_validation.ok) {
    return error(checkpoint.next_state, transition_validation.failures.front());
  }
  if (request.mode == RunMode::PLAN_ONLY) {
    return runPlanOnly(checkpoint.next_state, request, ObservationResult{snapshot, std::nullopt});
  }
  return runExecuteWorkflow(
    checkpoint.next_state, request, snapshot, checkpoint.sequence + 1);
}

RunResult StateMachineRunner::handleActionFailure(
  State state, IStateExecutor & executor, Failure original_failure,
  std::uint64_t checkpoint_sequence) const
{
  const auto stopped = stopAndObserveAfterFailure(executor);
  if (!stopped.snapshot) {
    return error(state, stopped.failure.value_or(Failure{FailureCategory::OBSERVATION,
               "POST_FAILURE_OBSERVATION_FAILED",
               "Unable to establish a stopped world after action failure", {}}));
  }
  original_failure.metrics["cancel_succeeded"] = 1.0;
  original_failure.metrics["arm_stationary_after_cancel"] = 1.0;
  const TransitionTable transitions;
  if (!isForwardAction(state) ||
    transitions.resolve(state, ActionStatus::FAILED) == State::ERROR)
  {
    return error(state, std::move(original_failure));
  }
  if (recovery_policy_ == nullptr) {
    return error(state, {FailureCategory::CONFIGURATION, "RECOVERY_POLICY_MISSING",
               "A recoverable action failure requires an IRecoveryPolicy", {}});
  }
  const auto route = recovery_policy_->select(state, original_failure, *stopped.snapshot);
  if (!route.next_state) {
    auto route_failure = route.failure.value_or(Failure{FailureCategory::INTERNAL,
          "RECOVERY_ROUTE_MISSING", "Recovery policy did not select a safe route", {}});
    return error(state, withOriginalFailure(std::move(route_failure), original_failure));
  }
  if (isForwardAction(*route.next_state) || isTerminal(*route.next_state)) {
    return error(state, {FailureCategory::CONFIGURATION, "RECOVERY_ROUTE_INVALID",
               "Recovery policy selected a forward or terminal state", {}});
  }
  Checkpoint checkpoint;
  checkpoint.run_id = "pick_place_state_machine";
  checkpoint.sequence = checkpoint_sequence;
  checkpoint.phase = CheckpointPhase::RECOVERY;
  checkpoint.last_completed_state = state;
  checkpoint.failed_state = state;
  checkpoint.original_failure = original_failure;
  checkpoint.next_state = *route.next_state;
  setExpectedWorldState(checkpoint, *stopped.snapshot);
  checkpoint.configuration_hash = common_resume_validator_->configurationHash();
  checkpoint.simulation_session_id = common_resume_validator_->simulationSessionId();
  if (const auto checkpoint_failure = checkpoint_store_->commit(checkpoint)) {
    return error(state, *checkpoint_failure);
  }
  return {RunStatus::RUNNING, state, route.next_state, std::move(original_failure), 1};
}

RunResult StateMachineRunner::error(State state, Failure failure, std::uint64_t transition_count)
{
  static_cast<void>(state);
  return {RunStatus::ERROR, State::ERROR, std::nullopt, std::move(failure), transition_count};
}

StateMachineRunner::StopObservationResult StateMachineRunner::stopAndObserveAfterFailure(
  IStateExecutor & executor) const
{
  const auto cancelled = executor.cancel();
  if (cancelled.status != ActionStatus::SUCCEEDED) {
    return {std::nullopt, cancelled.failure.value_or(Failure{FailureCategory::EXECUTION,
          "CANCEL_FAILED",
          "Failed to stop the trajectory after an execution or validation failure", {}})};
  }
  const auto deadline = std::chrono::steady_clock::now() + kStationaryTimeout;
  std::optional<ObservationResult> latest_observation;
  do {
    latest_observation = observer_->observe();
    if (!latest_observation->snapshot) {
      return {std::nullopt,
        latest_observation->failure.value_or(Failure{FailureCategory::OBSERVATION,
            "POST_FAILURE_OBSERVATION_FAILED", "Unable to observe after cancelling motion", {}})};
    }
    if (latest_observation->snapshot->fresh && latest_observation->snapshot->arm_stationary) {
      return {*latest_observation->snapshot, std::nullopt};
    }
    std::this_thread::sleep_for(kStationaryPollInterval);
  } while (std::chrono::steady_clock::now() < deadline);
  return {std::nullopt,
    Failure{FailureCategory::POSTCONDITION, "ARM_NOT_QUIESCENT_AFTER_CANCEL",
      "Motion was cancelled but the robot did not become stationary before the timeout",
      {{"cancel_succeeded", 1.0}, {"arm_stationary_after_cancel", 0.0}}}};
}

}  // namespace panda_gazebo_demo::pick_place
