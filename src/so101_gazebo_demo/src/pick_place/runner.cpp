#include "so101_gazebo_demo/pick_place/runner.hpp"

#include <chrono>
#include <thread>
#include <utility>

namespace so101_gazebo_demo::pick_place
{
namespace
{

constexpr auto kStationaryTimeout = std::chrono::seconds(2);
constexpr auto kStationaryPollInterval = std::chrono::milliseconds(25);
StateActionRegistry kEmptyActions;
TransitionContractRegistry kEmptyContracts;

bool isForwardAction(State state) noexcept
{
  return state >= State::PREPARE_OPEN_GRIPPER && state <= State::RETREAT;
}

bool requiresPlanning(State state) noexcept
{
  switch (state) {
    case State::MOVE_ABOVE_OBJECT:
    case State::DESCEND:
    case State::LIFT:
    case State::MOVE_ABOVE_PLACE:
    case State::DESCEND_TO_PLACE:
    case State::RETREAT:
    case State::RECOVER_LIFT_TO_SAFE_HEIGHT:
    case State::RECOVER_MOVE_ABOVE_PICK:
    case State::RECOVER_DESCEND_TO_PICK:
    case State::RECOVER_RETREAT:
      return true;
    default:
      return false;
  }
}

WorldSnapshot snapshotFromExpected(const ExpectedWorldState & expected,
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
  checkpoint.expected.required_world_objects.clear();
  for (const auto & [object_name, unused] : snapshot.moveit_world_object_poses) {
    static_cast<void>(unused);
    checkpoint.expected.required_world_objects.push_back(object_name);
  }
}

std::optional<State> successfulPredecessor(State state)
{
  std::optional<State> predecessor;
  for (const auto & [candidate, transitions] : TransitionTable::entries()) {
    if (transitions.succeeded != state) {
      continue;
    }
    if (predecessor) {
      return std::nullopt;
    }
    predecessor = candidate;
  }
  return predecessor;
}

Failure withOriginalFailure(Failure recovery_failure, const Failure & original_failure)
{
  recovery_failure.message +=
    " | original failure " + original_failure.code + ": " + original_failure.message;
  for (const auto & [name, value] : original_failure.metrics) {
    recovery_failure.metrics["original_" + name] = value;
  }
  return recovery_failure;
}

bool environmentEvidenceUnavailable(const Failure & failure) noexcept
{
  return failure.category == FailureCategory::OBSERVATION ||
         failure.category == FailureCategory::WORLD_INCONSISTENCY ||
         failure.category == FailureCategory::MOVEIT_SCENE ||
         failure.category == FailureCategory::TF;
}

}  // namespace

StateMachineRunner::StateMachineRunner() : StateMachineRunner(kEmptyActions, kEmptyContracts) {}

StateMachineRunner::StateMachineRunner(const StateActionRegistry & actions,
                                       const TransitionContractRegistry & contracts,
                                       IWorldObserver * observer,
                                       ICheckpointStore * checkpoint_store,
                                       const CommonResumeValidator * common_resume_validator,
                                       const PlanValidatorRegistry * plan_validators,
                                       const IRecoveryPolicy * recovery_policy) :
    actions_(actions), contracts_(contracts), observer_(observer),
    checkpoint_store_(checkpoint_store), common_resume_validator_(common_resume_validator),
    plan_validators_(plan_validators), recovery_policy_(recovery_policy)
{
}

RunResult StateMachineRunner::run(const RunRequest & request) const
{
  if (request.max_state_transitions == 0) {
    return error({FailureCategory::CONFIGURATION,
                  "INVALID_MAX_TRANSITIONS",
                  "max_state_transitions must be greater than zero",
                  {}});
  }
  if (request.fail_at && request.mode != RunMode::DRY_RUN) {
    return error({FailureCategory::CONFIGURATION,
                  "FAIL_AT_MODE_MISMATCH",
                  "fail_at is supported only in dry_run mode",
                  {}});
  }
  if (request.mode == RunMode::EXECUTE) {
    if (const auto configuration_failure = validateExecuteConfiguration()) {
      return error(*configuration_failure);
    }
  }
  if (request.resume) {
    return runResume(request);
  }
  switch (request.mode) {
    case RunMode::DRY_RUN:
      return runDryRun(request);
    case RunMode::PLAN_ONLY:
      return runPlanOnly(request.stop_after.value_or(State::MOVE_ABOVE_OBJECT), request);
    case RunMode::EXECUTE:
      return runExecuteWorkflow(State::PREPARE_OPEN_GRIPPER, request, std::nullopt, 1, 1,
                                CheckpointPhase::FORWARD, std::nullopt, std::nullopt, true);
  }
  return error({FailureCategory::INTERNAL, "UNKNOWN_MODE", "unknown run mode", {}});
}

std::optional<Failure> StateMachineRunner::validateExecuteConfiguration() const
{
  if (!observer_ || !checkpoint_store_ || !common_resume_validator_) {
    return Failure{FailureCategory::CONFIGURATION,
                   "EXECUTE_INFRASTRUCTURE_MISSING",
                   "execute requires observer, checkpoint store, and common resume validator",
                   {}};
  }
  if (!recovery_policy_) {
    return Failure{FailureCategory::CONFIGURATION,
                   "RECOVERY_POLICY_MISSING",
                   "execute requires a recovery policy before any action",
                   {}};
  }
  for (const auto & [state, transitions] : TransitionTable::entries()) {
    if (state == State::IDLE || isTerminal(state)) {
      continue;
    }
    if (!actions_.findExecutor(state)) {
      return Failure{FailureCategory::CONFIGURATION,
                     "EXECUTE_ACTION_NOT_REGISTERED",
                     std::string("State requires an executor: ") + toString(state),
                     {}};
    }
    if (!contracts_.hasContract({state, transitions.succeeded})) {
      return Failure{FailureCategory::CONFIGURATION,
                     "MISSING_TRANSITION_CONTRACT",
                     std::string("Missing execute contract for ") + toString(state) + " -> " +
                       toString(transitions.succeeded),
                     {}};
    }
    const bool has_planner = actions_.findPlanner(state) != nullptr;
    const bool has_plan_validator = plan_validators_ && plan_validators_->hasValidator(state);
    if (has_planner != has_plan_validator) {
      return has_planner
               ? Failure{FailureCategory::CONFIGURATION,
                         "PLAN_VALIDATOR_NOT_REGISTERED",
                         std::string("Planner has no paired plan validator for ") + toString(state),
                         {}}
               : Failure{FailureCategory::CONFIGURATION,
                         "PLANNER_NOT_REGISTERED",
                         std::string("Plan validator has no paired planner for ") + toString(state),
                         {}};
    }
    if (!requiresPlanning(state)) {
      continue;
    }
    if (!has_planner) {
      return Failure{FailureCategory::CONFIGURATION,
                     "PLANNER_NOT_REGISTERED",
                     std::string("State requires a planner: ") + toString(state),
                     {}};
    }
    if (!has_plan_validator) {
      return Failure{FailureCategory::CONFIGURATION,
                     "PLAN_VALIDATOR_NOT_REGISTERED",
                     std::string("State requires a plan validator: ") + toString(state),
                     {}};
    }
  }
  return std::nullopt;
}

RunResult StateMachineRunner::runDryRun(const RunRequest & request)
{
  StateMachine machine;
  RunResult result;
  result.status = RunStatus::RUNNING;
  result.state_trace.push_back(State::IDLE);
  while (!machine.isTerminal() && result.transition_count < request.max_state_transitions) {
    const auto state = machine.currentState();
    const auto status = request.fail_at == state ? ActionStatus::FAILED : ActionStatus::SUCCEEDED;
    const auto next = machine.advance(status);
    ++result.transition_count;
    result.state_trace.push_back(next);
    if (status != ActionStatus::SUCCEEDED) {
      result.failure = {FailureCategory::INTERNAL,
                        "DRY_RUN_FAILURE_INJECTED",
                        std::string("dry_run failure injected at ") + toString(state),
                        {}};
    }
    if (status == ActionStatus::SUCCEEDED && request.stop_after == state) {
      result.status = RunStatus::CHECKPOINT_COMPLETE;
      result.current_state = next;
      result.next_state = next;
      return result;
    }
  }
  result.current_state = machine.currentState();
  if (!machine.isTerminal()) {
    result.status = RunStatus::ERROR;
    result.failure = {FailureCategory::INTERNAL,
                      "MAX_TRANSITIONS_EXCEEDED",
                      "state machine exceeded max_state_transitions",
                      {}};
    result.state_trace.push_back(State::ERROR);
    result.current_state = State::ERROR;
    return result;
  }
  result.status = result.current_state == State::DONE ? RunStatus::DONE : RunStatus::ERROR;
  return result;
}

RunResult StateMachineRunner::runPlanOnly(State state, const RunRequest & request,
                                          std::optional<ObservationResult> observation) const
{
  if (!isAction(state) || isTerminal(state)) {
    return error({FailureCategory::CONFIGURATION,
                  "PLAN_ONLY_STATE_INVALID",
                  "plan_only requires a non-terminal action state",
                  {}});
  }
  auto * planner = actions_.findPlanner(state);
  if (!planner) {
    return error({FailureCategory::PLANNING,
                  "PLANNER_NOT_REGISTERED",
                  std::string("No planner is registered for ") + toString(state),
                  {}});
  }
  if (!plan_validators_ || !plan_validators_->hasValidator(state)) {
    return error({FailureCategory::CONFIGURATION,
                  "PLAN_VALIDATOR_NOT_REGISTERED",
                  std::string("No plan validator is registered for ") + toString(state),
                  {}});
  }
  if (!contracts_.hasContract({state, TransitionTable::resolve(state, ActionStatus::SUCCEEDED)})) {
    return error({FailureCategory::CONFIGURATION,
                  "MISSING_TRANSITION_CONTRACT",
                  "plan_only requires a precondition contract",
                  {}});
  }
  if (!observation) {
    if (!observer_) {
      return error({FailureCategory::CONFIGURATION,
                    "TARGET_OBSERVER_MISSING",
                    "plan_only requires a world observer",
                    {}});
    }
    observation = observer_->observe();
  }
  if (!observation->snapshot) {
    return error(
      observation->failure.value_or(Failure{FailureCategory::OBSERVATION,
                                            "TARGET_OBSERVATION_FAILED",
                                            "could not observe the world before planning",
                                            {}}));
  }
  const auto next_state = TransitionTable::resolve(state, ActionStatus::SUCCEEDED);
  const auto precondition =
    contracts_.validatePrecondition({state, next_state}, *observation->snapshot);
  if (!precondition.ok) {
    return error(precondition.failures.front());
  }
  const auto plan = planner->plan(state, next_state, *observation);
  if (plan.action.status != ActionStatus::SUCCEEDED || !plan.artifact) {
    return error(plan.action.failure.value_or(
      Failure{FailureCategory::PLANNING, "EMPTY_PLAN_ARTIFACT", "planner returned no plan", {}}));
  }
  const auto validation = plan_validators_->validate(state, *observation->snapshot, *plan.artifact);
  if (!validation.ok) {
    return error(validation.failures.front());
  }
  if (!request.stop_after) {
    return {RunStatus::PLAN_ONLY_COMPLETE, state, next_state, std::nullopt, 0, {state}};
  }
  const auto predecessor = successfulPredecessor(state);
  if (!predecessor || !checkpoint_store_ || !common_resume_validator_) {
    return error({FailureCategory::CONFIGURATION,
                  "PLAN_ONLY_CHECKPOINT_INFRASTRUCTURE_MISSING",
                  "plan_only stop boundary requires a unique predecessor and checkpoint services",
                  {}});
  }
  Checkpoint checkpoint;
  checkpoint.run_id = "pick_place_state_machine";
  checkpoint.sequence = 1;
  checkpoint.source_mode = RunMode::PLAN_ONLY;
  checkpoint.phase = CheckpointPhase::FORWARD;
  checkpoint.last_completed_state = *predecessor;
  checkpoint.next_state = state;
  checkpoint.configuration_hash = common_resume_validator_->configurationHash();
  checkpoint.simulation_session_id = common_resume_validator_->simulationSessionId();
  setExpectedWorldState(checkpoint, *observation->snapshot);
  if (const auto checkpoint_failure = checkpoint_store_->commit(checkpoint)) {
    return error(*checkpoint_failure);
  }
  return {RunStatus::CHECKPOINT_COMPLETE, state, state, std::nullopt, 0, {state}};
}

RunResult StateMachineRunner::runExecuteWorkflow(
  State initial_state, const RunRequest & request, std::optional<WorldSnapshot> initial_snapshot,
  std::uint64_t checkpoint_sequence, std::uint64_t initial_transition_count, CheckpointPhase phase,
  std::optional<State> failed_state, std::optional<Failure> original_failure,
  bool include_idle) const
{
  State state = initial_state;
  std::uint64_t transition_count = initial_transition_count;
  std::optional<Failure> workflow_failure = std::move(original_failure);
  std::vector<State> trace;
  if (include_idle) {
    trace.push_back(State::IDLE);
  }
  trace.push_back(state);
  while (!isTerminal(state) && transition_count < request.max_state_transitions) {
    const auto step = runExecuteStep(state, initial_snapshot, checkpoint_sequence, phase,
                                     failed_state, workflow_failure);
    initial_snapshot.reset();
    ++transition_count;
    if (step.status == RunStatus::ERROR) {
      auto failed = step;
      if (phase == CheckpointPhase::RECOVERY && workflow_failure && failed.failure) {
        failed.failure = withOriginalFailure(*failed.failure, *workflow_failure);
      }
      failed.transition_count = transition_count;
      trace.push_back(State::ERROR);
      failed.state_trace = std::move(trace);
      return failed;
    }
    if (!step.next_state) {
      auto failed = error({FailureCategory::INTERNAL,
                           "WORKFLOW_NEXT_STATE_MISSING",
                           "successful execute step did not provide a next state",
                           {}},
                          transition_count);
      trace.push_back(State::ERROR);
      failed.state_trace = std::move(trace);
      return failed;
    }
    trace.push_back(*step.next_state);
    if (step.status == RunStatus::CHECKPOINT_COMPLETE && request.stop_after == state) {
      auto stopped = step;
      stopped.transition_count = transition_count;
      stopped.state_trace = std::move(trace);
      return stopped;
    }
    if (phase == CheckpointPhase::FORWARD && step.failure && !isForwardAction(*step.next_state)) {
      phase = CheckpointPhase::RECOVERY;
      failed_state = state;
      workflow_failure = step.failure;
    } else if (phase == CheckpointPhase::RECOVERY && step.failure) {
      workflow_failure = step.failure;
    }
    state = *step.next_state;
    if (step.status == RunStatus::CHECKPOINT_COMPLETE) {
      ++checkpoint_sequence;
    }
  }
  if (!isTerminal(state)) {
    auto failed = error({FailureCategory::INTERNAL,
                         "MAX_TRANSITIONS_EXCEEDED",
                         "state machine exceeded max_state_transitions",
                         {}},
                        transition_count);
    trace.push_back(State::ERROR);
    failed.state_trace = std::move(trace);
    return failed;
  }
  RunResult result;
  result.status = state == State::DONE ? RunStatus::DONE : RunStatus::ERROR;
  result.current_state = state;
  result.transition_count = transition_count;
  result.state_trace = std::move(trace);
  if (state == State::ERROR) {
    result.failure =
      workflow_failure.value_or(Failure{FailureCategory::INTERNAL,
                                        "WORKFLOW_REACHED_ERROR",
                                        "workflow reached ERROR without a recorded failure",
                                        {}});
  }
  return result;
}

RunResult StateMachineRunner::runExecuteStep(State state, std::optional<WorldSnapshot> before,
                                             std::uint64_t checkpoint_sequence,
                                             CheckpointPhase phase,
                                             std::optional<State> failed_state,
                                             std::optional<Failure> original_failure) const
{
  const auto next_state = TransitionTable::resolve(state, ActionStatus::SUCCEEDED);
  if (!observer_ || !checkpoint_store_) {
    return error({FailureCategory::CONFIGURATION,
                  "EXECUTE_INFRASTRUCTURE_MISSING",
                  "execute requires a world observer and checkpoint store",
                  {}});
  }
  if (!common_resume_validator_) {
    return error({FailureCategory::CONFIGURATION,
                  "COMMON_RESUME_VALIDATOR_MISSING",
                  "execute requires a common resume validator",
                  {}});
  }
  if (phase == CheckpointPhase::RECOVERY && (!failed_state || !original_failure)) {
    return error({FailureCategory::CONFIGURATION,
                  "RECOVERY_EXECUTION_CONTEXT_INCOMPLETE",
                  "recovery requires failed state and original failure",
                  {}});
  }
  auto * executor = actions_.findExecutor(state);
  if (!executor) {
    return error({FailureCategory::CONFIGURATION,
                  "EXECUTE_ACTION_NOT_REGISTERED",
                  std::string("State requires an executor: ") + toString(state),
                  {}});
  }
  if (!contracts_.hasContract({state, next_state})) {
    return error({FailureCategory::CONFIGURATION,
                  "MISSING_TRANSITION_CONTRACT",
                  std::string("Missing execute contract for ") + toString(state) + " -> " +
                    toString(next_state),
                  {}});
  }
  if (!actions_.findPlanner(state) && plan_validators_ && plan_validators_->hasValidator(state)) {
    return error({FailureCategory::PLANNING,
                  "PLANNER_NOT_REGISTERED",
                  std::string("No planner is registered for ") + toString(state),
                  {}});
  }
  if (!before) {
    const auto observed = observer_->observe();
    if (!observed.snapshot) {
      const auto observation_failure =
        observed.failure.value_or(Failure{FailureCategory::OBSERVATION,
                                          "PRE_EXECUTION_OBSERVATION_FAILED",
                                          "could not observe before execution",
                                          {}});
      return error(observation_failure);
    }
    before = *observed.snapshot;
  }
  const auto precondition = contracts_.validatePrecondition({state, next_state}, *before);
  if (!precondition.ok) {
    if (environmentEvidenceUnavailable(precondition.failures.front())) {
      return error(precondition.failures.front());
    }
    return phase == CheckpointPhase::FORWARD
             ? handleActionFailure(state, *executor, precondition.failures.front(),
                                   checkpoint_sequence)
             : error(precondition.failures.front());
  }
  std::shared_ptr<const PlanArtifact> plan_artifact;
  if (auto * planner = actions_.findPlanner(state)) {
    if (!plan_validators_ || !plan_validators_->hasValidator(state)) {
      return error({FailureCategory::CONFIGURATION,
                    "PLAN_VALIDATOR_NOT_REGISTERED",
                    std::string("No plan validator is registered for ") + toString(state),
                    {}});
    }
    const ObservationResult planning_observation{*before, std::nullopt};
    const auto plan = planner->plan(state, next_state, planning_observation);
    if (plan.action.status != ActionStatus::SUCCEEDED || !plan.artifact) {
      auto planning_failure =
        plan.action.failure.value_or(Failure{FailureCategory::PLANNING,
                                             "EMPTY_PLAN_ARTIFACT",
                                             "planner returned no usable trajectory",
                                             {}});
      if (environmentEvidenceUnavailable(planning_failure)) {
        return error(planning_failure);
      }
      return phase == CheckpointPhase::FORWARD
               ? handleActionFailure(state, *executor, planning_failure, checkpoint_sequence)
               : error(planning_failure);
    }
    const auto validation = plan_validators_->validate(state, *before, *plan.artifact);
    if (!validation.ok) {
      return phase == CheckpointPhase::FORWARD
               ? handleActionFailure(state, *executor, validation.failures.front(),
                                     checkpoint_sequence)
               : error(validation.failures.front());
    }
    plan_artifact = plan.artifact;
  }
  const auto action = executor->execute({state, next_state, *before, plan_artifact});
  if (action.status != ActionStatus::SUCCEEDED) {
    return handleActionFailure(
      state, *executor,
      action.failure.value_or(
        Failure{FailureCategory::EXECUTION, "EXECUTION_FAILED", "trajectory execution failed", {}}),
      checkpoint_sequence);
  }
  const auto after = observer_->observe();
  if (!after.snapshot) {
    return handleActionFailure(state, *executor,
                               after.failure.value_or(Failure{FailureCategory::OBSERVATION,
                                                              "POST_EXECUTION_OBSERVATION_FAILED",
                                                              "could not observe after execution",
                                                              {}}),
                               checkpoint_sequence);
  }
  const auto transition =
    contracts_.validate({state, next_state}, *before, *after.snapshot, action);
  if (!transition.ok) {
    return handleActionFailure(state, *executor, transition.failures.front(), checkpoint_sequence);
  }
  Checkpoint checkpoint;
  checkpoint.run_id = "pick_place_state_machine";
  checkpoint.sequence = checkpoint_sequence;
  checkpoint.source_mode = RunMode::EXECUTE;
  checkpoint.phase = phase;
  checkpoint.last_completed_state = state;
  checkpoint.failed_state = failed_state;
  checkpoint.original_failure = original_failure;
  checkpoint.next_state = next_state;
  checkpoint.configuration_hash = common_resume_validator_->configurationHash();
  checkpoint.simulation_session_id = common_resume_validator_->simulationSessionId();
  setExpectedWorldState(checkpoint, *after.snapshot);
  if (const auto checkpoint_failure = checkpoint_store_->commit(checkpoint)) {
    if (phase == CheckpointPhase::FORWARD) {
      return handleActionFailure(state, *executor, *checkpoint_failure, checkpoint_sequence);
    }
    return error(*checkpoint_failure);
  }
  return {RunStatus::CHECKPOINT_COMPLETE, state, next_state, std::nullopt, 1, {}};
}

RunResult StateMachineRunner::runResume(const RunRequest & request) const
{
  if (request.mode == RunMode::DRY_RUN) {
    return error({FailureCategory::CONFIGURATION,
                  "RESUME_DRY_RUN_UNSUPPORTED",
                  "resume is supported only in plan_only and execute modes",
                  {}});
  }
  if (!observer_ || !checkpoint_store_ || !common_resume_validator_) {
    return error({FailureCategory::RESUME_VALIDATION,
                  "RESUME_INFRASTRUCTURE_MISSING",
                  "resume requires observer, checkpoint store, and common validator",
                  {}});
  }
  const auto loaded = checkpoint_store_->loadLatestCompatible();
  if (!loaded.checkpoint) {
    return error(loaded.failure.value_or(
      Failure{FailureCategory::CHECKPOINT, "CHECKPOINT_LOAD_FAILED", "unable to load", {}}));
  }
  const auto & checkpoint = *loaded.checkpoint;
  const bool source_mode_supported =
    checkpoint.source_mode == RunMode::EXECUTE || checkpoint.source_mode == RunMode::PLAN_ONLY;
  const bool invalid_forward_transition =
    checkpoint.phase == CheckpointPhase::FORWARD &&
    (isTerminal(checkpoint.last_completed_state) ||
     TransitionTable::resolve(checkpoint.last_completed_state, ActionStatus::SUCCEEDED) !=
       checkpoint.next_state);
  const bool invalid_recovery_context = checkpoint.phase == CheckpointPhase::RECOVERY &&
                                        (!checkpoint.failed_state || !checkpoint.original_failure);
  const bool invalid_recovery_source =
    checkpoint.phase == CheckpointPhase::RECOVERY && checkpoint.source_mode != RunMode::EXECUTE;
  if (checkpoint.schema_version != 3 || !source_mode_supported || !checkpoint.resumable ||
      invalid_forward_transition || invalid_recovery_context || invalid_recovery_source) {
    return error({FailureCategory::RESUME_VALIDATION,
                  "CHECKPOINT_INCOMPATIBLE",
                  "checkpoint does not describe a resumable boundary",
                  {}});
  }
  const auto observation = observer_->observe();
  if (!observation.snapshot) {
    return error(observation.failure.value_or(Failure{FailureCategory::OBSERVATION,
                                                      "RESUME_OBSERVATION_FAILED",
                                                      "unable to observe while resuming",
                                                      {}}));
  }
  const auto common = common_resume_validator_->validate(checkpoint, *observation.snapshot);
  if (!common.ok) {
    return error(common.failures.front());
  }
  if (checkpoint.phase == CheckpointPhase::RECOVERY) {
    if (!recovery_policy_) {
      return error({FailureCategory::CONFIGURATION,
                    "RECOVERY_POLICY_MISSING",
                    "recovery resume requires a recovery policy",
                    {}});
    }
    const auto route = recovery_policy_->select(
      *checkpoint.failed_state, *checkpoint.original_failure, *observation.snapshot);
    if (!route.next_state) {
      return error(route.failure.value_or(
        Failure{FailureCategory::INTERNAL, "RECOVERY_ROUTE_MISSING", "route missing", {}}));
    }
    if (isForwardAction(*route.next_state) || isTerminal(*route.next_state)) {
      return error({FailureCategory::CONFIGURATION,
                    "RECOVERY_ROUTE_INVALID",
                    "recovery policy selected a forward or terminal state",
                    {}});
    }
    if (request.mode == RunMode::PLAN_ONLY) {
      return runPlanOnly(*route.next_state, request, observation);
    }
    return runExecuteWorkflow(*route.next_state, request, *observation.snapshot,
                              checkpoint.sequence + 1, 0, CheckpointPhase::RECOVERY,
                              checkpoint.failed_state, checkpoint.original_failure);
  }
  const TransitionKey resumed_transition{checkpoint.last_completed_state, checkpoint.next_state};
  if (!contracts_.hasContract(resumed_transition)) {
    return error({FailureCategory::CONFIGURATION,
                  "MISSING_TRANSITION_CONTRACT",
                  "resume requires a transition contract",
                  {}});
  }
  const auto boundary = contracts_.validateResume(
    resumed_transition, snapshotFromExpected(checkpoint.expected, checkpoint.simulation_session_id),
    *observation.snapshot);
  if (!boundary.ok) {
    return error(boundary.failures.front());
  }
  if (request.mode == RunMode::PLAN_ONLY) {
    return runPlanOnly(checkpoint.next_state, request, observation);
  }
  return runExecuteWorkflow(checkpoint.next_state, request, *observation.snapshot,
                            checkpoint.sequence + 1, 0);
}

RunResult StateMachineRunner::handleActionFailure(State state, IStateExecutor & executor,
                                                  Failure original_failure,
                                                  std::uint64_t checkpoint_sequence) const
{
  const auto stopped = stopAndObserveAfterFailure(executor);
  if (!stopped.snapshot) {
    return error(stopped.failure.value_or(Failure{FailureCategory::OBSERVATION,
                                                  "POST_FAILURE_OBSERVATION_FAILED",
                                                  "unable to establish a stopped world",
                                                  {}}));
  }
  original_failure.metrics["cancel_succeeded"] = 1.0;
  original_failure.metrics["arm_stationary_after_cancel"] = 1.0;
  if (!isForwardAction(state) ||
      TransitionTable::resolve(state, ActionStatus::FAILED) == State::ERROR) {
    return error(std::move(original_failure));
  }
  if (!recovery_policy_) {
    return error({FailureCategory::CONFIGURATION,
                  "RECOVERY_POLICY_MISSING",
                  "recoverable failure requires a recovery policy",
                  {}});
  }
  const auto route = recovery_policy_->select(state, original_failure, *stopped.snapshot);
  if (!route.next_state) {
    return error(route.failure.value_or(
      Failure{FailureCategory::INTERNAL, "RECOVERY_ROUTE_MISSING", "route missing", {}}));
  }
  if (isForwardAction(*route.next_state) || isTerminal(*route.next_state)) {
    return error({FailureCategory::CONFIGURATION,
                  "RECOVERY_ROUTE_INVALID",
                  "recovery policy selected a forward or terminal state",
                  {}});
  }
  Checkpoint checkpoint;
  checkpoint.run_id = "pick_place_state_machine";
  checkpoint.sequence = checkpoint_sequence;
  checkpoint.source_mode = RunMode::EXECUTE;
  checkpoint.phase = CheckpointPhase::RECOVERY;
  checkpoint.last_completed_state = state;
  checkpoint.failed_state = state;
  checkpoint.original_failure = original_failure;
  checkpoint.next_state = *route.next_state;
  checkpoint.configuration_hash = common_resume_validator_->configurationHash();
  checkpoint.simulation_session_id = common_resume_validator_->simulationSessionId();
  setExpectedWorldState(checkpoint, *stopped.snapshot);
  if (const auto checkpoint_failure = checkpoint_store_->commit(checkpoint)) {
    original_failure.message += " | checkpoint persistence failed: " + checkpoint_failure->code;
    original_failure.metrics["recovery_checkpoint_persisted"] = 0.0;
  } else {
    original_failure.metrics["recovery_checkpoint_persisted"] = 1.0;
  }
  return {RunStatus::RUNNING, state, route.next_state, std::move(original_failure), 1, {}};
}

StateMachineRunner::StopObservationResult
StateMachineRunner::stopAndObserveAfterFailure(IStateExecutor & executor) const
{
  const auto cancelled = executor.cancel();
  if (cancelled.status != ActionStatus::SUCCEEDED) {
    return {std::nullopt,
            cancelled.failure.value_or(
              Failure{FailureCategory::EXECUTION, "CANCEL_FAILED", "failed to stop action", {}})};
  }
  const auto deadline = std::chrono::steady_clock::now() + kStationaryTimeout;
  do {
    const auto observed = observer_->observe();
    if (!observed.snapshot) {
      return {std::nullopt, observed.failure.value_or(Failure{FailureCategory::OBSERVATION,
                                                              "POST_FAILURE_OBSERVATION_FAILED",
                                                              "unable to observe after cancel",
                                                              {}})};
    }
    if (observed.snapshot->fresh && observed.snapshot->arm_stationary) {
      return {*observed.snapshot, std::nullopt};
    }
    std::this_thread::sleep_for(kStationaryPollInterval);
  } while (std::chrono::steady_clock::now() < deadline);
  return {std::nullopt, Failure{FailureCategory::POSTCONDITION,
                                "ARM_NOT_QUIESCENT_AFTER_CANCEL",
                                "action cancelled but world did not become stationary",
                                {{"cancel_succeeded", 1.0}, {"arm_stationary_after_cancel", 0.0}}}};
}

RunResult StateMachineRunner::error(Failure failure, std::uint64_t transition_count)
{
  return {RunStatus::ERROR, State::ERROR, std::nullopt, std::move(failure), transition_count, {}};
}

}  // namespace so101_gazebo_demo::pick_place
