#include "panda_gazebo_demo/pick_place/runner.hpp"

namespace panda_gazebo_demo::pick_place
{

namespace
{

constexpr double kResumeTcpPositionTolerance = 0.02;

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
    case RunMode::EXECUTE:
      return runExecuteMoveAboveObject(request);
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

RunResult StateMachineRunner::runPlanOnly(State state, const RunRequest & request) const
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
  const auto plan = planner->plan(state);
  if (plan.action.status != ActionStatus::SUCCEEDED || !plan.artifact ||
    plan.artifact->trajectory_points == 0)
  {
    return error(state, plan.action.failure.value_or(Failure{
        FailureCategory::PLAN_VALIDATION, "EMPTY_PLAN_ARTIFACT",
        "Planner returned no usable trajectory", {}}));
  }
  const TransitionTable transitions;
  return {RunStatus::PLAN_ONLY_COMPLETE, state,
    transitions.resolve(state, ActionStatus::SUCCEEDED), std::nullopt, 0};
}

RunResult StateMachineRunner::runExecuteMoveAboveObject(const RunRequest & request) const
{
  constexpr State state_to_execute = State::MOVE_ABOVE_OBJECT;
  constexpr State next_state = State::DESCEND;
  if (request.stop_after != state_to_execute) {
    return error(State::IDLE, {FailureCategory::CONFIGURATION, "EXECUTE_SCOPE_REJECTED",
               "execute is currently allowed only with stop_after=MOVE_ABOVE_OBJECT", {}});
  }
  return runExecuteStep(state_to_execute, next_state, request);
}

RunResult StateMachineRunner::runExecuteStep(
  State state, State next_state, const RunRequest & request, std::optional<WorldSnapshot> before,
  std::uint64_t checkpoint_sequence) const
{
  if (request.stop_after != state) {
    return error(state, {FailureCategory::CONFIGURATION, "EXECUTE_SCOPE_REJECTED",
               std::string("execute requires stop_after=") + toString(state), {}});
  }
  if (observer_ == nullptr || checkpoint_store_ == nullptr) {
    return error(state, {FailureCategory::CONFIGURATION, "EXECUTE_INFRASTRUCTURE_MISSING",
               "execute requires a world observer and checkpoint store", {}});
  }
  auto * planner = actions_.findPlanner(state);
  auto * executor = actions_.findExecutor(state);
  if (planner == nullptr || executor == nullptr) {
    return error(state, {FailureCategory::CONFIGURATION, "EXECUTE_ACTION_NOT_REGISTERED",
               std::string("State requires both planner and executor: ") + toString(state), {}});
  }
  if (!contracts_.hasContract({state, next_state})) {
    return error(state, {FailureCategory::CONFIGURATION, "MISSING_TRANSITION_CONTRACT",
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
  const auto precondition = contracts_.validatePrecondition({state, next_state}, *before);
  if (!precondition.ok) {
    return error(state, precondition.failures.front());
  }
  const auto plan = planner->plan(state);
  if (plan.action.status != ActionStatus::SUCCEEDED || !plan.artifact ||
    plan.artifact->trajectory_points == 0)
  {
    return error(state, plan.action.failure.value_or(Failure{
        FailureCategory::PLAN_VALIDATION, "EMPTY_PLAN_ARTIFACT",
        "Planner returned no usable trajectory", {}}));
  }
  const auto action = executor->execute(state, plan.artifact);
  if (action.status != ActionStatus::SUCCEEDED) {
    return error(state, action.failure.value_or(Failure{
        FailureCategory::EXECUTION, "EXECUTION_FAILED", "Trajectory execution failed", {}}));
  }
  const auto after = observer_->observe();
  if (!after.snapshot) {
    return error(state, after.failure.value_or(Failure{
        FailureCategory::OBSERVATION, "POST_EXECUTION_OBSERVATION_FAILED",
        "Could not observe the world after execution", {}}));
  }
  const auto validation = contracts_.validate({state, next_state}, *before, *after.snapshot,
      action);
  if (!validation.ok) {
    return error(state, validation.failures.front());
  }
  Checkpoint checkpoint;
  checkpoint.run_id = "pick_place_state_machine";
  checkpoint.sequence = checkpoint_sequence;
  checkpoint.last_completed_state = state;
  checkpoint.next_state = next_state;
  checkpoint.expected.tcp_pose_world = after.snapshot->tcp_pose_world;
  checkpoint.expected.coke_attached = after.snapshot->coke_attached;
  for (const auto & [object_id, pose] : after.snapshot->world_object_poses) {
    static_cast<void>(pose);
    checkpoint.expected.required_world_objects.push_back(object_id);
  }
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
  if (checkpoint.schema_version != 1 || checkpoint.source_mode != RunMode::EXECUTE ||
    !checkpoint.resumable || checkpoint.last_completed_state != State::MOVE_ABOVE_OBJECT ||
    checkpoint.next_state != State::DESCEND)
  {
    return error(State::IDLE, {FailureCategory::RESUME_VALIDATION, "CHECKPOINT_INCOMPATIBLE",
               "Checkpoint is not a resumable MOVE_ABOVE_OBJECT -> DESCEND checkpoint", {}});
  }
  const auto observation = observer_->observe();
  if (!observation.snapshot) {
    return error(checkpoint.next_state, observation.failure.value_or(Failure{
        FailureCategory::RESUME_VALIDATION, "RESUME_OBSERVATION_FAILED",
        "Unable to observe the world while resuming", {}}));
  }
  const auto & snapshot = *observation.snapshot;
  if (!snapshot.fresh || !snapshot.arm_stationary ||
    snapshot.coke_attached != checkpoint.expected.coke_attached ||
    positionDistance(snapshot.tcp_pose_world, checkpoint.expected.tcp_pose_world) >
    kResumeTcpPositionTolerance)
  {
    return error(checkpoint.next_state, {FailureCategory::RESUME_VALIDATION,
               "RESUME_WORLD_MISMATCH",
               "Current TCP, attachment state, or robot motion does not match checkpoint", {}});
  }
  for (const auto & object_id : checkpoint.expected.required_world_objects) {
    if (snapshot.world_object_poses.count(object_id) == 0) {
      return error(checkpoint.next_state, {FailureCategory::RESUME_VALIDATION,
                 "RESUME_REQUIRED_WORLD_OBJECT_MISSING",
                 "Required Planning Scene object is missing during resume: " + object_id, {}});
    }
  }
  if (request.mode == RunMode::PLAN_ONLY) {
    return runPlanOnly(checkpoint.next_state, request);
  }
  if (request.stop_after != checkpoint.next_state) {
    return error(checkpoint.next_state,
             {FailureCategory::CONFIGURATION, "RESUME_EXECUTE_SCOPE_REJECTED",
               "resume execute requires stop_after=DESCEND", {}});
  }
  return runExecuteStep(
    checkpoint.next_state, State::CLOSE_GRIPPER, request, snapshot, checkpoint.sequence + 1);
}

RunResult StateMachineRunner::error(State state, Failure failure, std::uint64_t transition_count)
{
  return {RunStatus::ERROR, state, std::nullopt, std::move(failure), transition_count};
}

}  // namespace panda_gazebo_demo::pick_place
