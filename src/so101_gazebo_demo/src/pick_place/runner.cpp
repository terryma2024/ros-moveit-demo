#include "so101_gazebo_demo/pick_place/runner.hpp"

namespace so101_gazebo_demo::pick_place
{
namespace
{
StateActionRegistry kEmptyActions;
TransitionContractRegistry kEmptyContracts;

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
  checkpoint.expected.required_world_objects.clear();
  for (const auto & [object_name, unused] : snapshot.moveit_world_object_poses) {
    (void)unused;
    checkpoint.expected.required_world_objects.push_back(object_name);
  }
}
}  // namespace

StateMachineRunner::StateMachineRunner() : StateMachineRunner(kEmptyActions, kEmptyContracts) {}

StateMachineRunner::StateMachineRunner(const StateActionRegistry & actions,
                                       const TransitionContractRegistry & contracts,
                                       IWorldObserver * observer, ICheckpointStore * store,
                                       const CommonResumeValidator * resume,
                                       const PlanValidatorRegistry * validators,
                                       const IRecoveryPolicy * recovery) :
    actions_(actions), contracts_(contracts), observer_(observer), store_(store), resume_(resume),
    validators_(validators), recovery_(recovery)
{
}

RunResult StateMachineRunner::error(Failure failure) const
{
  return {RunStatus::ERROR, State::ERROR, {}, std::move(failure), 0, {}};
}

RunResult StateMachineRunner::dry(const RunRequest & request) const
{
  StateMachine machine;
  RunResult result;
  result.status = RunStatus::RUNNING;
  result.state_trace.push_back(State::IDLE);
  while (!machine.isTerminal() && result.transition_count < request.max_state_transitions) {
    const auto state = machine.currentState();
    const auto next =
      machine.advance(request.fail_at == state ? ActionStatus::FAILED : ActionStatus::SUCCEEDED);
    ++result.transition_count;
    result.state_trace.push_back(next);
    if (request.fail_at == state) {
      result.failure =
        Failure{FailureCategory::INTERNAL, "DRY_RUN_FAILURE_INJECTED", "injected", {}};
    }
    if (request.stop_after == state && request.fail_at != state) {
      result.status = RunStatus::CHECKPOINT_COMPLETE;
      result.current_state = next;
      result.next_state = next;
      return result;
    }
  }
  result.current_state = machine.currentState();
  result.status = result.current_state == State::DONE ? RunStatus::DONE : RunStatus::ERROR;
  return result;
}

RunResult StateMachineRunner::execute(State state, const RunRequest & request,
                                      std::optional<WorldSnapshot> before,
                                      std::uint64_t sequence) const
{
  RunResult result;
  result.status = RunStatus::RUNNING;
  while (!isTerminal(state) && result.transition_count < request.max_state_transitions) {
    result.state_trace.push_back(state);
    const auto next = TransitionTable::resolve(state, ActionStatus::SUCCEEDED);
    auto * executor = actions_.findExecutor(state);
    if (!observer_ || !store_ || !resume_ || !executor) {
      return error({FailureCategory::CONFIGURATION,
                    "EXECUTE_INFRASTRUCTURE_MISSING",
                    "missing observer/store/validator/executor",
                    {}});
    }
    if (!contracts_.hasContract({state, next})) {
      return error(
        {FailureCategory::CONFIGURATION, "MISSING_TRANSITION_CONTRACT", "contract missing", {}});
    }
    auto observation = before ? ObservationResult{before, {}} : observer_->observe();
    before.reset();
    if (!observation.snapshot) {
      return error({FailureCategory::OBSERVATION,
                    "PRE_EXECUTION_OBSERVATION_FAILED",
                    "observation missing",
                    {}});
    }
    std::shared_ptr<const PlanArtifact> plan;
    if (auto * planner = actions_.findPlanner(state)) {
      if (!validators_ || !validators_->hasValidator(state)) {
        return error({FailureCategory::CONFIGURATION,
                      "PLAN_VALIDATOR_NOT_REGISTERED",
                      "validator missing",
                      {}});
      }
      auto plan_result = planner->plan(state, next, observation);
      if (plan_result.action.status != ActionStatus::SUCCEEDED || !plan_result.artifact) {
        return error({FailureCategory::PLANNING, "PLAN_FAILED", "plan failed", {}});
      }
      if (!validators_->validate(state, *observation.snapshot, *plan_result.artifact).ok) {
        return error({FailureCategory::PLAN_VALIDATION, "PLAN_INVALID", "plan invalid", {}});
      }
      plan = plan_result.artifact;
    }
    const auto action = executor->execute({state, next, *observation.snapshot, plan});
    if (action.status != ActionStatus::SUCCEEDED) {
      executor->cancel();
      auto stopped = observer_->observe();
      const auto original_failure = action.failure.value_or(
        Failure{FailureCategory::EXECUTION, "EXECUTION_FAILED", "execution failed", {}});
      if (!stopped.snapshot || !recovery_) {
        return error(original_failure);
      }
      const auto route = recovery_->select(state, original_failure, *stopped.snapshot);
      if (!route.next_state) {
        return error(route.failure.value_or(
          Failure{FailureCategory::INTERNAL, "RECOVERY_ROUTE_MISSING", "route missing", {}}));
      }
      Checkpoint checkpoint;
      checkpoint.sequence = sequence++;
      checkpoint.source_mode = request.mode;
      checkpoint.phase = CheckpointPhase::RECOVERY;
      checkpoint.last_completed_state = state;
      checkpoint.failed_state = state;
      checkpoint.original_failure = original_failure;
      checkpoint.next_state = *route.next_state;
      checkpoint.configuration_hash = resume_->configurationHash();
      checkpoint.simulation_session_id = resume_->simulationSessionId();
      setExpectedWorldState(checkpoint, *stopped.snapshot);
      if (const auto failure = store_->commit(checkpoint)) {
        return error(*failure);
      }
      state = *route.next_state;
      continue;
    }
    auto after = observer_->observe();
    if (!after.snapshot ||
        !contracts_.validate({state, next}, *observation.snapshot, *after.snapshot, action).ok) {
      return error(
        {FailureCategory::POSTCONDITION, "POSTCONDITION_FAILED", "postcondition failed", {}});
    }
    Checkpoint checkpoint;
    checkpoint.sequence = sequence++;
    checkpoint.source_mode = request.mode;
    checkpoint.last_completed_state = state;
    checkpoint.next_state = next;
    checkpoint.configuration_hash = resume_->configurationHash();
    checkpoint.simulation_session_id = resume_->simulationSessionId();
    setExpectedWorldState(checkpoint, *after.snapshot);
    if (const auto failure = store_->commit(checkpoint)) {
      return error(*failure);
    }
    ++result.transition_count;
    if (request.stop_after == state) {
      result.status = RunStatus::CHECKPOINT_COMPLETE;
      result.current_state = next;
      result.next_state = next;
      return result;
    }
    state = next;
  }
  result.current_state = state;
  result.status = state == State::DONE ? RunStatus::DONE : RunStatus::ERROR;
  return result;
}

RunResult StateMachineRunner::run(const RunRequest & request) const
{
  if (request.mode == RunMode::DRY_RUN) {
    return dry(request);
  }
  if (request.resume) {
    if (!store_ || !observer_ || !resume_) {
      return error({FailureCategory::RESUME_VALIDATION,
                    "RESUME_INFRASTRUCTURE_MISSING",
                    "resume infra missing",
                    {}});
    }
    const auto loaded = store_->loadLatestCompatible();
    if (!loaded.checkpoint) {
      return error(loaded.failure.value_or(
        Failure{FailureCategory::CHECKPOINT, "CHECKPOINT_LOAD_FAILED", "load failed", {}}));
    }
    auto observation = observer_->observe();
    if (!observation.snapshot) {
      return error(
        {FailureCategory::OBSERVATION, "RESUME_OBSERVATION_FAILED", "observe failed", {}});
    }
    if (!resume_->validate(*loaded.checkpoint, *observation.snapshot).ok) {
      return error(
        {FailureCategory::RESUME_VALIDATION, "RESUME_BOUNDARY_INVALID", "boundary invalid", {}});
    }
    return execute(loaded.checkpoint->next_state, request, *observation.snapshot,
                   loaded.checkpoint->sequence + 1);
  }
  if (request.mode == RunMode::PLAN_ONLY) {
    auto * planner = actions_.findPlanner(State::MOVE_ABOVE_OBJECT);
    if (!planner || !observer_ || !validators_) {
      return error({FailureCategory::CONFIGURATION,
                    "PLAN_ONLY_INFRASTRUCTURE_MISSING",
                    "plan infra missing",
                    {}});
    }
    auto observation = observer_->observe();
    if (!observation.snapshot) {
      return error(
        {FailureCategory::OBSERVATION, "TARGET_OBSERVATION_FAILED", "observe failed", {}});
    }
    const auto plan = planner->plan(State::MOVE_ABOVE_OBJECT, State::DESCEND, observation);
    if (plan.action.status != ActionStatus::SUCCEEDED || !plan.artifact ||
        !validators_->validate(State::MOVE_ABOVE_OBJECT, *observation.snapshot, *plan.artifact)
           .ok) {
      return error({FailureCategory::PLAN_VALIDATION, "PLAN_INVALID", "plan invalid", {}});
    }
    return {RunStatus::PLAN_ONLY_COMPLETE, State::MOVE_ABOVE_OBJECT, State::DESCEND, {}, 0,
            {State::MOVE_ABOVE_OBJECT}};
  }
  return execute(State::PREPARE_OPEN_GRIPPER, request, {}, 1);
}

}  // namespace so101_gazebo_demo::pick_place
