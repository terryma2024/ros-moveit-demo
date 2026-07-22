#include "panda_gazebo_demo/pick_place/runner.hpp"

namespace panda_gazebo_demo::pick_place
{

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
    return error(State::IDLE, {FailureCategory::RESUME_VALIDATION, "RESUME_NOT_IMPLEMENTED",
               "resume requires a compatible, revalidated execute checkpoint", {}});
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
  if (request.stop_after.has_value()) {
    return error(State::IDLE, {FailureCategory::CONFIGURATION, "STOP_AFTER_PLAN_ONLY_UNSUPPORTED",
               "plan_only plans one next state and does not create a checkpoint", {}});
  }

  constexpr State state_to_plan = State::MOVE_ABOVE_OBJECT;
  auto * planner = actions_.findPlanner(state_to_plan);
  if (planner == nullptr) {
    return error(state_to_plan, {FailureCategory::PLANNING, "PLANNER_NOT_REGISTERED",
               "No planner is registered for MOVE_ABOVE_OBJECT", {}});
  }
  const auto plan = planner->plan(state_to_plan);
  if (plan.action.status != ActionStatus::SUCCEEDED || !plan.artifact ||
    plan.artifact->trajectory_points == 0)
  {
    return error(state_to_plan, plan.action.failure.value_or(Failure{
        FailureCategory::PLAN_VALIDATION, "EMPTY_PLAN_ARTIFACT",
        "Planner returned no usable trajectory", {}}));
  }
  return {RunStatus::PLAN_ONLY_COMPLETE, state_to_plan, State::DESCEND, std::nullopt, 0};
}

RunResult StateMachineRunner::runExecuteMoveAboveObject(const RunRequest & request) const
{
  constexpr State state_to_execute = State::MOVE_ABOVE_OBJECT;
  constexpr State next_state = State::DESCEND;
  if (request.stop_after != state_to_execute) {
    return error(State::IDLE, {FailureCategory::CONFIGURATION, "EXECUTE_SCOPE_REJECTED",
               "execute is currently allowed only with stop_after=MOVE_ABOVE_OBJECT", {}});
  }
  if (observer_ == nullptr || checkpoint_store_ == nullptr) {
    return error(state_to_execute,
             {FailureCategory::CONFIGURATION, "EXECUTE_INFRASTRUCTURE_MISSING",
               "execute requires a world observer and checkpoint store", {}});
  }
  auto * planner = actions_.findPlanner(state_to_execute);
  auto * executor = actions_.findExecutor(state_to_execute);
  if (planner == nullptr || executor == nullptr) {
    return error(state_to_execute, {FailureCategory::CONFIGURATION, "EXECUTE_ACTION_NOT_REGISTERED",
               "MOVE_ABOVE_OBJECT requires both planner and executor", {}});
  }
  if (!contracts_.hasContract({state_to_execute, next_state})) {
    return error(state_to_execute, {FailureCategory::CONFIGURATION, "MISSING_TRANSITION_CONTRACT",
               "MOVE_ABOVE_OBJECT -> DESCEND requires an explicit contract", {}});
  }
  const auto before = observer_->observe();
  if (!before.snapshot) {
    return error(state_to_execute, before.failure.value_or(Failure{
        FailureCategory::OBSERVATION, "PRE_EXECUTION_OBSERVATION_FAILED",
        "Could not observe the world before execution", {}}));
  }
  const auto precondition = contracts_.validatePrecondition(
    {state_to_execute, next_state}, *before.snapshot);
  if (!precondition.ok) {
    return error(state_to_execute, precondition.failures.front());
  }
  const auto plan = planner->plan(state_to_execute);
  if (plan.action.status != ActionStatus::SUCCEEDED || !plan.artifact ||
    plan.artifact->trajectory_points == 0)
  {
    return error(state_to_execute, plan.action.failure.value_or(Failure{
        FailureCategory::PLAN_VALIDATION, "EMPTY_PLAN_ARTIFACT",
        "Planner returned no usable trajectory", {}}));
  }
  const auto action = executor->execute(state_to_execute, plan.artifact);
  if (action.status != ActionStatus::SUCCEEDED) {
    return error(state_to_execute, action.failure.value_or(Failure{
        FailureCategory::EXECUTION, "EXECUTION_FAILED", "Trajectory execution failed", {}}));
  }
  const auto after = observer_->observe();
  if (!after.snapshot) {
    return error(state_to_execute, after.failure.value_or(Failure{
        FailureCategory::OBSERVATION, "POST_EXECUTION_OBSERVATION_FAILED",
        "Could not observe the world after execution", {}}));
  }
  const auto validation = contracts_.validate(
    {state_to_execute, next_state}, *before.snapshot, *after.snapshot, action);
  if (!validation.ok) {
    return error(state_to_execute, validation.failures.front());
  }
  Checkpoint checkpoint;
  checkpoint.run_id = "move_above_object";
  checkpoint.sequence = 1;
  checkpoint.last_completed_state = state_to_execute;
  checkpoint.next_state = next_state;
  checkpoint.expected.tcp_pose_world = after.snapshot->tcp_pose_world;
  checkpoint.expected.coke_attached = after.snapshot->coke_attached;
  for (const auto & [object_id, pose] : after.snapshot->world_object_poses) {
    static_cast<void>(pose);
    checkpoint.expected.required_world_objects.push_back(object_id);
  }
  if (const auto checkpoint_failure = checkpoint_store_->commit(checkpoint)) {
    return error(state_to_execute, *checkpoint_failure);
  }
  return {RunStatus::CHECKPOINT_COMPLETE, state_to_execute, next_state, std::nullopt, 1};
}

RunResult StateMachineRunner::error(State state, Failure failure, std::uint64_t transition_count)
{
  return {RunStatus::ERROR, state, std::nullopt, std::move(failure), transition_count};
}

}  // namespace panda_gazebo_demo::pick_place
