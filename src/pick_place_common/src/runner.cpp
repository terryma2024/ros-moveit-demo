#include "pick_place_common/runner.hpp"

#include <algorithm>
#include <chrono>
#include <thread>
#include <utility>

#include "pick_place_common/run_request_validation.hpp"

namespace pick_place_common
{

namespace
{

constexpr auto kStationaryTimeout = std::chrono::seconds(2);
constexpr auto kStationaryPollInterval = std::chrono::milliseconds(25);

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
  snapshot.moveit_task_object_attached = expected.moveit_task_object_attached;
  snapshot.gazebo_task_object_pose_world = expected.gazebo_task_object_pose_world;
  snapshot.gazebo_task_object_attached = expected.gazebo_task_object_attached;
  snapshot.gazebo_task_object_stationary = expected.gazebo_task_object_stationary;
  snapshot.simulation_session_id = simulation_session_id;
  return snapshot;
}

void setExpectedWorldState(Checkpoint & checkpoint, const WorldSnapshot & snapshot)
{
  checkpoint.expected.tcp_pose_world = snapshot.tcp_pose_world;
  checkpoint.expected.gripper_open = snapshot.gripper_open;
  checkpoint.expected.joint_positions = snapshot.joint_positions;
  checkpoint.expected.moveit_world_object_poses = snapshot.moveit_world_object_poses;
  checkpoint.expected.moveit_task_object_attached = snapshot.moveit_task_object_attached;
  checkpoint.expected.gazebo_task_object_pose_world = snapshot.gazebo_task_object_pose_world;
  checkpoint.expected.gazebo_task_object_attached = snapshot.gazebo_task_object_attached;
  checkpoint.expected.gazebo_task_object_stationary = snapshot.gazebo_task_object_stationary;
  for (const auto & [object_id, pose] : snapshot.moveit_world_object_poses) {
    static_cast<void>(pose);
    checkpoint.expected.required_world_objects.push_back(object_id);
  }
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

Failure withCheckpointPersistenceFailure(Failure workflow_failure,
                                         const Failure & checkpoint_failure)
{
  workflow_failure.message += " | recovery checkpoint persistence failure " +
                              checkpoint_failure.code + ": " + checkpoint_failure.message;
  workflow_failure.metrics["recovery_checkpoint_persisted"] = 0.0;
  return workflow_failure;
}

}  // namespace

StateMachineRunner::StateMachineRunner(
  const WorkflowDefinition & workflow, const StateActionRegistry & actions,
  const TransitionContractRegistry & contracts, IWorldObserver * observer,
  ICheckpointStore * checkpoint_store, const CommonResumeValidator * resume_validator,
  IExecutionObservationSink * observation_sink, const PlanValidatorRegistry * plan_validators,
  const IRecoveryPolicy * recovery_policy, const IRunnerBehaviorPolicy * behavior_policy) :
    workflow_(workflow), actions_(actions), contracts_(contracts), observer_(observer),
    checkpoint_store_(checkpoint_store), resume_validator_(resume_validator),
    observation_sink_(observation_sink), plan_validators_(plan_validators),
    recovery_policy_(recovery_policy), behavior_policy_(behavior_policy)
{
}

State StateMachineRunner::resolve(State state, ActionStatus status) const
{
  const auto found = workflow_.transitions.find(state);
  if (found == workflow_.transitions.end()) {
    return State::ERROR;
  }
  return status == ActionStatus::SUCCEEDED ? found->second.succeeded : found->second.failed;
}

bool StateMachineRunner::terminal(State state) const
{
  return workflow_.terminal_states.count(state) != 0;
}

bool StateMachineRunner::forwardAction(State state) const
{
  return workflow_.forward_states.count(state) != 0 && workflow_.action_states.count(state) != 0;
}

RunResult StateMachineRunner::run(const RunRequest & request) const
{
  if (const auto failure = validateRunRequest(workflow_, request)) {
    return error(State::IDLE, *failure);
  }
  const bool plan_only = request.mode == RunMode::PLAN_ONLY;
  if (plan_only || (behavior_policy_ && request.mode == RunMode::EXECUTE)) {
    if (!observer_ || !checkpoint_store_ || !resume_validator_) {
      return error(State::IDLE,
                   {FailureCategory::CONFIGURATION,
                    "EXECUTE_INFRASTRUCTURE_MISSING",
                    "execute requires observer, checkpoint store, and resume validator",
                    {}});
    }
    if (!recovery_policy_) {
      return error(State::IDLE, {FailureCategory::CONFIGURATION,
                                 "RECOVERY_POLICY_MISSING",
                                 "executable modes require a recovery policy",
                                 {}});
    }
    std::vector<State> required_states;
    if (plan_only) {
      State state = resolve(workflow_.initial_state, ActionStatus::SUCCEEDED);
      while (!terminal(state)) {
        required_states.push_back(state);
        if (state == *request.plan_only_state) {
          break;
        }
        state = resolve(state, ActionStatus::SUCCEEDED);
      }
    } else {
      required_states.assign(workflow_.action_states.begin(), workflow_.action_states.end());
    }
    for (const auto state : required_states) {
      const auto transition = workflow_.transitions.find(state);
      if (transition == workflow_.transitions.end()) {
        continue;
      }
      if (!actions_.findExecutor(state)) {
        return error(state, {FailureCategory::CONFIGURATION,
                             "EXECUTE_ACTION_NOT_REGISTERED",
                             std::string("State requires an executor: ") + toString(state),
                             {}});
      }
      if (!contracts_.hasContract({state, transition->second.succeeded})) {
        return error(state, {FailureCategory::CONFIGURATION,
                             "MISSING_TRANSITION_CONTRACT",
                             std::string("Missing execute contract for ") + toString(state),
                             {}});
      }
      const bool has_planner = actions_.findPlanner(state) != nullptr;
      const bool has_validator = plan_validators_ && plan_validators_->hasValidator(state);
      if (has_planner != has_validator) {
        return error(state,
                     {FailureCategory::CONFIGURATION,
                      has_planner ? "PLAN_VALIDATOR_NOT_REGISTERED" : "PLANNER_NOT_REGISTERED",
                      "planner and plan validator registrations must be paired",
                      {}});
      }
      if (plan_only && state == *request.plan_only_state && !has_planner) {
        return error(state, {FailureCategory::CONFIGURATION,
                             "PLANNER_NOT_REGISTERED",
                             std::string("No planner is registered for ") + toString(state),
                             {}});
      }
    }
  }
  if (request.resume) {
    return runResume(request);
  }
  switch (request.mode) {
    case RunMode::DRY_RUN:
      return runDryRun(request);
    case RunMode::PLAN_ONLY:
      return runExecuteWorkflow(resolve(workflow_.initial_state, ActionStatus::SUCCEEDED), request,
                                std::nullopt, 1, 1, CheckpointPhase::FORWARD, std::nullopt,
                                std::nullopt, true);
    case RunMode::EXECUTE:
      return runExecuteWorkflow(resolve(workflow_.initial_state, ActionStatus::SUCCEEDED), request,
                                std::nullopt, 1, 1, CheckpointPhase::FORWARD, std::nullopt,
                                std::nullopt,
                                behavior_policy_ && behavior_policy_->includeIdleInTrace());
  }
  return error(State::IDLE, {FailureCategory::INTERNAL, "UNKNOWN_MODE", "Unknown run mode", {}});
}

RunResult StateMachineRunner::runDryRun(const RunRequest & request) const
{
  StateMachine state_machine(workflow_, workflow_.initial_state);
  std::uint64_t transition_count = 0;
  std::optional<Failure> injected_failure;
  std::vector<State> trace{state_machine.currentState()};
  while (!state_machine.isTerminal() && transition_count < request.max_state_transitions) {
    const auto current = state_machine.currentState();
    const auto status = request.fail_at == current ? ActionStatus::FAILED : ActionStatus::SUCCEEDED;
    const auto next = state_machine.advance(status);
    ++transition_count;
    trace.push_back(next);
    if (status != ActionStatus::SUCCEEDED) {
      injected_failure = Failure{FailureCategory::INTERNAL,
                                 "DRY_RUN_FAILURE_INJECTED",
                                 std::string("dry_run failure injected at ") + toString(current),
                                 {}};
    }
    if (status == ActionStatus::SUCCEEDED && request.stop_after == current) {
      return {RunStatus::CHECKPOINT_COMPLETE, next, next, std::nullopt, transition_count, trace};
    }
  }
  if (!state_machine.isTerminal()) {
    return error(state_machine.currentState(),
                 {FailureCategory::INTERNAL,
                  "STATE_TRANSITION_BUDGET_EXHAUSTED",
                  "State machine exceeded max_state_transitions",
                  {}},
                 transition_count);
  }
  return {state_machine.currentState() == State::DONE ? RunStatus::DONE : RunStatus::ERROR,
          state_machine.currentState(),
          std::nullopt,
          injected_failure,
          transition_count,
          trace};
}

RunResult StateMachineRunner::runPlanOnlyTarget(State state, const RunRequest & request,
                                                std::optional<ObservationResult> observation,
                                                std::uint64_t checkpoint_sequence) const
{
  static_cast<void>(request);
  auto * executor = actions_.findExecutor(state);
  if (executor == nullptr) {
    return error(state, {FailureCategory::CONFIGURATION,
                         "EXECUTE_ACTION_NOT_REGISTERED",
                         std::string("State requires an executor: ") + toString(state),
                         {}});
  }
  auto * planner = actions_.findPlanner(state);
  if (planner == nullptr) {
    return error(state, {FailureCategory::PLANNING,
                         "PLANNER_NOT_REGISTERED",
                         std::string("No planner is registered for ") + toString(state),
                         {}});
  }
  if (plan_validators_ == nullptr || !plan_validators_->hasValidator(state)) {
    return error(state, {FailureCategory::CONFIGURATION,
                         "PLAN_VALIDATOR_NOT_REGISTERED",
                         std::string("No plan validator is registered for ") + toString(state),
                         {}});
  }
  if (!observation) {
    if (observer_ == nullptr) {
      return error(state, {FailureCategory::CONFIGURATION,
                           "TARGET_OBSERVER_MISSING",
                           "plan_only requires an observer for target policy input",
                           {}});
    }
    observation = observer_->observe();
  }
  if (!observation->snapshot) {
    return handleActionFailure(
      state, *executor,
      observation->failure.value_or(Failure{FailureCategory::OBSERVATION,
                                            "TARGET_OBSERVATION_FAILED",
                                            "Could not observe the world before planning",
                                            {}}),
      checkpoint_sequence);
  }
  const auto next_state = resolve(state, ActionStatus::SUCCEEDED);
  const auto precondition =
    contracts_.validatePrecondition({state, next_state}, *observation->snapshot);
  if (!precondition.ok) {
    return handleActionFailure(state, *executor, precondition.failures.front(),
                               checkpoint_sequence);
  }
  const auto plan = planner->plan(state, next_state, *observation);
  if (plan.action.status != ActionStatus::SUCCEEDED || !plan.artifact) {
    return handleActionFailure(
      state, *executor,
      plan.action.failure.value_or(Failure{FailureCategory::PLAN_VALIDATION,
                                           "EMPTY_PLAN_ARTIFACT",
                                           "Planner returned no usable trajectory",
                                           {}}),
      checkpoint_sequence);
  }
  const auto plan_validation =
    plan_validators_->validate(state, *observation->snapshot, *plan.artifact);
  if (!plan_validation.ok) {
    return handleActionFailure(state, *executor, plan_validation.failures.front(),
                               checkpoint_sequence);
  }
  return {RunStatus::PLAN_ONLY_COMPLETE, state, next_state, std::nullopt, 0};
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
    trace.push_back(workflow_.initial_state);
  }
  trace.push_back(state);
  while (!terminal(state) && transition_count < request.max_state_transitions) {
    if (state == State::VALIDATION_FAILED) {
      return {RunStatus::CHECKPOINT_COMPLETE,
              state,
              state,
              workflow_failure,
              transition_count,
              std::move(trace)};
    }
    if (phase == CheckpointPhase::FORWARD && request.mode == RunMode::PLAN_ONLY &&
        state == *request.plan_only_state) {
      std::optional<ObservationResult> target_observation;
      if (initial_snapshot) {
        target_observation = ObservationResult{*initial_snapshot, std::nullopt};
      }
      initial_snapshot.reset();
      auto target =
        runPlanOnlyTarget(state, request, std::move(target_observation), checkpoint_sequence);
      if (target.status == RunStatus::PLAN_ONLY_COMPLETE) {
        target.transition_count = transition_count;
        target.state_trace = std::move(trace);
        return target;
      }
      ++transition_count;
      if (target.status == RunStatus::ERROR || !target.next_state) {
        if (target.failure && workflow_failure) {
          target.failure = withOriginalFailure(*target.failure, *workflow_failure);
        }
        target.transition_count = transition_count;
        trace.push_back(State::ERROR);
        target.state_trace = std::move(trace);
        return target;
      }
      trace.push_back(*target.next_state);
      phase = CheckpointPhase::RECOVERY;
      failed_state = state;
      workflow_failure = target.failure;
      ++checkpoint_sequence;
      state = *target.next_state;
      continue;
    }
    const auto step = runExecuteStep(state, initial_snapshot, checkpoint_sequence, phase,
                                     failed_state, workflow_failure);
    initial_snapshot.reset();
    ++transition_count;
    if (step.status == RunStatus::ERROR) {
      auto failed = step;
      if (phase == CheckpointPhase::RECOVERY && workflow_failure && step.failure) {
        failed.failure = withOriginalFailure(*step.failure, *workflow_failure);
      }
      failed.transition_count = transition_count;
      trace.push_back(State::ERROR);
      failed.state_trace = std::move(trace);
      return failed;
    }
    if (!step.next_state) {
      auto failed = error(state,
                          {FailureCategory::INTERNAL,
                           "WORKFLOW_NEXT_STATE_MISSING",
                           "Successful execute step did not provide its next state",
                           {}},
                          transition_count);
      trace.push_back(State::ERROR);
      failed.state_trace = std::move(trace);
      return failed;
    }
    trace.push_back(*step.next_state);
    if (step.status == RunStatus::CHECKPOINT_COMPLETE &&
        (request.stop_after == state || request.single_step)) {
      auto stopped = step;
      stopped.transition_count = transition_count;
      stopped.state_trace = std::move(trace);
      return stopped;
    }
    if (phase == CheckpointPhase::FORWARD && step.status == RunStatus::RUNNING && step.failure &&
        !forwardAction(*step.next_state)) {
      phase = CheckpointPhase::RECOVERY;
      failed_state = state;
      workflow_failure = step.failure;
      ++checkpoint_sequence;
    } else if (phase == CheckpointPhase::RECOVERY && step.status == RunStatus::RUNNING &&
               step.failure) {
      workflow_failure = step.failure;
    }
    state = *step.next_state;
    if (step.status == RunStatus::CHECKPOINT_COMPLETE) {
      ++checkpoint_sequence;
    }
  }
  if (!terminal(state)) {
    auto failed = error(state,
                        {FailureCategory::INTERNAL,
                         "MAX_TRANSITIONS_EXCEEDED",
                         "State machine exceeded max_state_transitions",
                         {}},
                        transition_count);
    trace.push_back(State::ERROR);
    failed.state_trace = std::move(trace);
    return failed;
  }
  if (state == State::DONE) {
    return {RunStatus::DONE, state, std::nullopt, std::nullopt, transition_count, std::move(trace)};
  }
  return {RunStatus::ERROR,
          State::ERROR,
          std::nullopt,
          workflow_failure.value_or(Failure{FailureCategory::INTERNAL,
                                            "WORKFLOW_REACHED_ERROR",
                                            "Workflow reached ERROR without a recorded failure",
                                            {}}),
          transition_count,
          std::move(trace)};
}

RunResult StateMachineRunner::runExecuteStep(State state, std::optional<WorldSnapshot> before,
                                             std::uint64_t checkpoint_sequence,
                                             CheckpointPhase phase,
                                             std::optional<State> failed_state,
                                             std::optional<Failure> original_failure) const
{
  const auto next_state = resolve(state, ActionStatus::SUCCEEDED);
  if (observer_ == nullptr || checkpoint_store_ == nullptr) {
    return error(state, {FailureCategory::CONFIGURATION,
                         "EXECUTE_INFRASTRUCTURE_MISSING",
                         "execute requires a world observer and checkpoint store",
                         {}});
  }
  if (phase == CheckpointPhase::RECOVERY && (!failed_state || !original_failure)) {
    return error(state, {FailureCategory::CONFIGURATION,
                         "RECOVERY_EXECUTION_CONTEXT_INCOMPLETE",
                         "Recovery execution requires the failed state and original failure",
                         {}});
  }
  auto * executor = actions_.findExecutor(state);
  if (executor == nullptr) {
    return error(state, {FailureCategory::CONFIGURATION,
                         "EXECUTE_ACTION_NOT_REGISTERED",
                         std::string("State requires an executor: ") + toString(state),
                         {}});
  }
  if (!contracts_.hasContract({state, next_state})) {
    return error(state, {FailureCategory::CONFIGURATION,
                         "MISSING_TRANSITION_CONTRACT",
                         std::string("Missing execute contract for ") + toString(state) + " -> " +
                           toString(next_state),
                         {}});
  }
  if (!before) {
    const auto observation = observer_->observe();
    if (!observation.snapshot) {
      auto failure =
        observation.failure.value_or(Failure{FailureCategory::OBSERVATION,
                                             "PRE_EXECUTION_OBSERVATION_FAILED",
                                             "Could not observe the world before execution",
                                             {}});
      if (phase == CheckpointPhase::FORWARD && !behavior_policy_) {
        return handleActionFailure(state, *executor, std::move(failure), checkpoint_sequence);
      }
      return error(state, std::move(failure));
    }
    before = *observation.snapshot;
  }
  const ObservationResult planning_observation{*before, std::nullopt};
  auto precondition = contracts_.validatePrecondition({state, next_state}, *before);
  std::size_t precondition_attempt = 0;
  while (!precondition.ok && !precondition.failures.empty() && behavior_policy_ &&
         behavior_policy_->retryPrecondition(state, precondition.failures.front(),
                                             precondition_attempt++)) {
    const auto observed = observer_->observe();
    if (!observed.snapshot) {
      if (observed.failure &&
          observed.failure->code == "ROBOT_STATE_CHANGED_DURING_MOVEIT_OBSERVATION") {
        continue;
      }
      return error(state,
                   observed.failure.value_or(Failure{FailureCategory::OBSERVATION,
                                                     "PRE_EXECUTION_OBSERVATION_FAILED",
                                                     "Could not observe precondition convergence",
                                                     {}}));
    }
    before = *observed.snapshot;
    precondition = contracts_.validatePrecondition({state, next_state}, *before);
  }
  if (!precondition.ok) {
    if (behavior_policy_) {
      const auto environment_failure = std::find_if(
        precondition.failures.begin(), precondition.failures.end(), [](const Failure & failure) {
          return failure.category == FailureCategory::OBSERVATION ||
                 failure.category == FailureCategory::WORLD_INCONSISTENCY ||
                 failure.category == FailureCategory::MOVEIT_SCENE ||
                 failure.category == FailureCategory::TF;
        });
      if (environment_failure != precondition.failures.end()) {
        return error(state, *environment_failure);
      }
    }
    if (phase == CheckpointPhase::FORWARD) {
      return handleActionFailure(state, *executor, precondition.failures.front(),
                                 checkpoint_sequence);
    }
    return error(state, precondition.failures.front());
  }
  std::shared_ptr<const PlanArtifact> plan_artifact;
  if (auto * planner = actions_.findPlanner(state)) {
    if (plan_validators_ == nullptr || !plan_validators_->hasValidator(state)) {
      return error(state, {FailureCategory::CONFIGURATION,
                           "PLAN_VALIDATOR_NOT_REGISTERED",
                           std::string("No plan validator is registered for ") + toString(state),
                           {}});
    }
    const auto plan = planner->plan(state, next_state, planning_observation);
    if (plan.action.status != ActionStatus::SUCCEEDED || !plan.artifact) {
      auto failure = plan.action.failure.value_or(Failure{FailureCategory::PLAN_VALIDATION,
                                                          "EMPTY_PLAN_ARTIFACT",
                                                          "Planner returned no usable trajectory",
                                                          {}});
      if (phase == CheckpointPhase::FORWARD) {
        return handleActionFailure(state, *executor, std::move(failure), checkpoint_sequence);
      }
      return error(state, std::move(failure));
    }
    const auto plan_validation = plan_validators_->validate(state, *before, *plan.artifact);
    if (!plan_validation.ok) {
      if (phase == CheckpointPhase::FORWARD) {
        return handleActionFailure(state, *executor, plan_validation.failures.front(),
                                   checkpoint_sequence);
      }
      return error(state, plan_validation.failures.front());
    }
    plan_artifact = plan.artifact;
  }
  const auto action = executor->execute({state, next_state, *before, plan_artifact});
  if (action.status != ActionStatus::SUCCEEDED) {
    return handleActionFailure(
      state, *executor,
      action.failure.value_or(
        Failure{FailureCategory::EXECUTION, "EXECUTION_FAILED", "Trajectory execution failed", {}}),
      checkpoint_sequence);
  }
  auto after = observer_->observe();
  std::size_t post_observation_attempt = 1;
  while (!after.snapshot && behavior_policy_ && after.failure &&
         after.failure->code == "ROBOT_STATE_CHANGED_DURING_MOVEIT_OBSERVATION" &&
         post_observation_attempt++ < 480) {
    after = observer_->observe();
  }
  if (!after.snapshot) {
    const auto observation_failure =
      after.failure.value_or(Failure{FailureCategory::OBSERVATION,
                                     "POST_EXECUTION_OBSERVATION_FAILED",
                                     "Could not observe the world after execution",
                                     {}});
    return handleActionFailure(state, *executor, observation_failure, checkpoint_sequence);
  }
  if (observation_sink_ != nullptr) {
    observation_sink_->record(state, *before, *after.snapshot);
  }
  auto validation = contracts_.validate({state, next_state}, *before, *after.snapshot, action);
  std::size_t postcondition_attempt = 0;
  while (!validation.ok && !validation.failures.empty() && behavior_policy_ &&
         behavior_policy_->retryPostcondition(state, validation.failures.front(),
                                              postcondition_attempt++)) {
    const auto observed = observer_->observe();
    if (!observed.snapshot) {
      if (observed.failure &&
          observed.failure->code == "ROBOT_STATE_CHANGED_DURING_MOVEIT_OBSERVATION") {
        continue;
      }
      return handleActionFailure(
        state, *executor,
        observed.failure.value_or(Failure{FailureCategory::OBSERVATION,
                                          "POST_EXECUTION_OBSERVATION_FAILED",
                                          "Could not observe endpoint convergence",
                                          {}}),
        checkpoint_sequence);
    }
    after = observed;
    validation = contracts_.validate({state, next_state}, *before, *after.snapshot, action);
  }
  if (!validation.ok) {
    return handleActionFailure(state, *executor, validation.failures.front(), checkpoint_sequence);
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
  checkpoint.simulation_session_id = resume_validator_ ? resume_validator_->simulationSessionId()
                                                       : after.snapshot->simulation_session_id;
  checkpoint.configuration_fingerprint =
    resume_validator_ ? resume_validator_->configurationFingerprint() : std::string{};
  if (const auto checkpoint_failure = checkpoint_store_->commit(checkpoint)) {
    if (phase == CheckpointPhase::FORWARD) {
      return handleActionFailure(state, *executor, *checkpoint_failure, checkpoint_sequence);
    }
    return {RunStatus::RUNNING, state, next_state,
            withCheckpointPersistenceFailure(*original_failure, *checkpoint_failure), 1};
  }
  return {RunStatus::CHECKPOINT_COMPLETE, state, next_state, std::nullopt, 1};
}

RunResult StateMachineRunner::runResume(const RunRequest & request) const
{
  if (request.mode == RunMode::DRY_RUN) {
    return error(State::IDLE, {FailureCategory::CONFIGURATION,
                               "RESUME_DRY_RUN_UNSUPPORTED",
                               "resume is supported only in plan_only and execute modes",
                               {}});
  }
  if (observer_ == nullptr || checkpoint_store_ == nullptr) {
    return error(State::IDLE, {FailureCategory::RESUME_VALIDATION,
                               "RESUME_INFRASTRUCTURE_MISSING",
                               "resume requires a world observer and checkpoint store",
                               {}});
  }
  const auto loaded = checkpoint_store_->loadLatestCompatible();
  if (!loaded.checkpoint) {
    return error(State::IDLE, loaded.failure.value_or(Failure{FailureCategory::CHECKPOINT,
                                                              "CHECKPOINT_LOAD_FAILED",
                                                              "Unable to load checkpoint",
                                                              {}}));
  }
  const auto & checkpoint = *loaded.checkpoint;
  const bool invalid_forward_transition =
    checkpoint.phase == CheckpointPhase::FORWARD &&
    (terminal(checkpoint.last_completed_state) ||
     resolve(checkpoint.last_completed_state, ActionStatus::SUCCEEDED) != checkpoint.next_state);
  const bool invalid_recovery_context = checkpoint.phase == CheckpointPhase::RECOVERY &&
                                        (!checkpoint.failed_state || !checkpoint.original_failure);
  if (checkpoint.schema_version != 3 || checkpoint.source_mode != RunMode::EXECUTE ||
      !checkpoint.resumable || invalid_forward_transition || invalid_recovery_context) {
    return error(State::IDLE,
                 {FailureCategory::RESUME_VALIDATION,
                  "CHECKPOINT_INCOMPATIBLE",
                  "Checkpoint does not describe a valid successful workflow transition",
                  {}});
  }
  const auto observation = observer_->observe();
  if (!observation.snapshot) {
    return error(checkpoint.next_state,
                 observation.failure.value_or(Failure{FailureCategory::RESUME_VALIDATION,
                                                      "RESUME_OBSERVATION_FAILED",
                                                      "Unable to observe the world while resuming",
                                                      {}}));
  }
  if (resume_validator_ == nullptr) {
    return error(checkpoint.next_state, {FailureCategory::RESUME_VALIDATION,
                                         "COMMON_RESUME_VALIDATOR_MISSING",
                                         "resume requires a CommonResumeValidator",
                                         {}});
  }
  auto snapshot = *observation.snapshot;
  const bool requires_stationary_coke =
    checkpoint.phase == CheckpointPhase::RECOVERY ||
    checkpoint.expected.gazebo_task_object_stationary.value_or(false);
  if (requires_stationary_coke) {
    const auto stationary_deadline = std::chrono::steady_clock::now() + kStationaryTimeout;
    while (!behavior_policy_ &&
           (!snapshot.gazebo_task_object_stationary || !*snapshot.gazebo_task_object_stationary) &&
           std::chrono::steady_clock::now() < stationary_deadline) {
      std::this_thread::sleep_for(kStationaryPollInterval);
      const auto settled_observation = observer_->observe();
      if (!settled_observation.snapshot) {
        return error(checkpoint.next_state,
                     settled_observation.failure.value_or(
                       Failure{FailureCategory::OBSERVATION,
                               "RESUME_SETTLE_OBSERVATION_FAILED",
                               "Unable to observe the world while waiting for resume to settle",
                               {}}));
      }
      snapshot = *settled_observation.snapshot;
    }
    if (!snapshot.gazebo_task_object_stationary || !*snapshot.gazebo_task_object_stationary) {
      const bool recovery = checkpoint.phase == CheckpointPhase::RECOVERY;
      return error(checkpoint.next_state,
                   {FailureCategory::PRECONDITION,
                    recovery ? "RECOVERY_COKE_NOT_STATIONARY" : "RESUME_COKE_NOT_STATIONARY",
                    "Gazebo Coke did not become stationary before resume",
                    {}});
    }
  }
  const auto common_validation = resume_validator_->validate(checkpoint, snapshot);
  if (!common_validation.ok) {
    return error(checkpoint.next_state, common_validation.failures.front());
  }
  if (checkpoint.phase == CheckpointPhase::RECOVERY) {
    if (recovery_policy_ == nullptr) {
      return error(checkpoint.next_state, {FailureCategory::CONFIGURATION,
                                           "RECOVERY_POLICY_MISSING",
                                           "Recovery resume requires an IRecoveryPolicy",
                                           {}});
    }
    const auto route =
      recovery_policy_->select(*checkpoint.failed_state, *checkpoint.original_failure, snapshot);
    if (!route.next_state) {
      auto route_failure =
        route.failure.value_or(Failure{FailureCategory::INTERNAL,
                                       "RECOVERY_ROUTE_MISSING",
                                       "Recovery policy did not select a safe route during resume",
                                       {}});
      return error(checkpoint.next_state,
                   withOriginalFailure(std::move(route_failure), *checkpoint.original_failure));
    }
    if (forwardAction(*route.next_state) || terminal(*route.next_state)) {
      return error(checkpoint.next_state,
                   {FailureCategory::CONFIGURATION,
                    "RECOVERY_ROUTE_INVALID",
                    "Recovery policy selected a forward or terminal state during resume",
                    {}});
    }
    if (request.mode == RunMode::PLAN_ONLY) {
      return runPlanOnlyTarget(*route.next_state, request,
                               ObservationResult{snapshot, std::nullopt}, checkpoint.sequence + 1);
    }
    return runExecuteWorkflow(*route.next_state, request, snapshot, checkpoint.sequence + 1, 0,
                              CheckpointPhase::RECOVERY, checkpoint.failed_state,
                              checkpoint.original_failure);
  }
  const TransitionKey resumed_transition{checkpoint.last_completed_state, checkpoint.next_state};
  if (!contracts_.hasContract(resumed_transition)) {
    return error(checkpoint.next_state, {FailureCategory::CONFIGURATION,
                                         "MISSING_TRANSITION_CONTRACT",
                                         "resume requires a transition validator",
                                         {}});
  }
  const auto transition_validation = contracts_.validateResume(
    resumed_transition, snapshotFromExpected(checkpoint.expected, checkpoint.simulation_session_id),
    snapshot);
  if (!transition_validation.ok) {
    return error(checkpoint.next_state, transition_validation.failures.front());
  }
  if (request.mode == RunMode::PLAN_ONLY) {
    return runPlanOnlyTarget(checkpoint.next_state, request,
                             ObservationResult{snapshot, std::nullopt}, checkpoint.sequence + 1);
  }
  return runExecuteWorkflow(checkpoint.next_state, request, snapshot, checkpoint.sequence + 1);
}

RunResult StateMachineRunner::handleActionFailure(State state, IStateExecutor & executor,
                                                  Failure original_failure,
                                                  std::uint64_t checkpoint_sequence) const
{
  const auto stopped = stopAndObserveAfterFailure(executor);
  if (!stopped.snapshot) {
    auto stop_failure =
      stopped.failure.value_or(Failure{FailureCategory::OBSERVATION,
                                       "POST_FAILURE_OBSERVATION_FAILED",
                                       "Unable to establish a stopped world after action failure",
                                       {}});
    if (behavior_policy_) {
      stop_failure = withOriginalFailure(std::move(stop_failure), original_failure);
    }
    return error(state, std::move(stop_failure));
  }
  original_failure.metrics["cancel_succeeded"] = 1.0;
  original_failure.metrics["arm_stationary_after_cancel"] = 1.0;
  if (!forwardAction(state) || resolve(state, ActionStatus::FAILED) == State::ERROR) {
    return error(state, std::move(original_failure));
  }
  if (recovery_policy_ == nullptr) {
    return error(state, {FailureCategory::CONFIGURATION,
                         "RECOVERY_POLICY_MISSING",
                         "A recoverable action failure requires an IRecoveryPolicy",
                         {}});
  }
  const auto route = recovery_policy_->select(state, original_failure, *stopped.snapshot);
  if (!route.next_state) {
    auto route_failure =
      route.failure.value_or(Failure{FailureCategory::INTERNAL,
                                     "RECOVERY_ROUTE_MISSING",
                                     "Recovery policy did not select a safe route",
                                     {}});
    return error(state, withOriginalFailure(std::move(route_failure), original_failure));
  }
  if (forwardAction(*route.next_state) || terminal(*route.next_state)) {
    return error(state, {FailureCategory::CONFIGURATION,
                         "RECOVERY_ROUTE_INVALID",
                         "Recovery policy selected a forward or terminal state",
                         {}});
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
  checkpoint.configuration_fingerprint =
    resume_validator_ ? resume_validator_->configurationFingerprint() : std::string{};
  checkpoint.simulation_session_id = resume_validator_ ? resume_validator_->simulationSessionId()
                                                       : stopped.snapshot->simulation_session_id;
  if (const auto checkpoint_failure = checkpoint_store_->commit(checkpoint)) {
    return {RunStatus::RUNNING, state, route.next_state,
            withCheckpointPersistenceFailure(std::move(original_failure), *checkpoint_failure), 1};
  }
  original_failure.metrics["recovery_checkpoint_persisted"] = 1.0;
  return {RunStatus::RUNNING, state, route.next_state, std::move(original_failure), 1};
}

RunResult StateMachineRunner::error(State state, Failure failure, std::uint64_t transition_count)
{
  static_cast<void>(state);
  return {RunStatus::ERROR, State::ERROR, std::nullopt, std::move(failure), transition_count};
}

StateMachineRunner::StopObservationResult
StateMachineRunner::stopAndObserveAfterFailure(IStateExecutor & executor) const
{
  const auto cancelled = executor.cancel();
  if (cancelled.status != ActionStatus::SUCCEEDED) {
    return {std::nullopt,
            cancelled.failure.value_or(
              Failure{FailureCategory::EXECUTION,
                      "CANCEL_FAILED",
                      "Failed to stop the trajectory after an execution or validation failure",
                      {}})};
  }
  const auto deadline = std::chrono::steady_clock::now() + kStationaryTimeout;
  std::optional<ObservationResult> latest_observation;
  do {
    latest_observation = observer_->observe();
    if (!latest_observation->snapshot) {
      if (behavior_policy_ && latest_observation->failure &&
          latest_observation->failure->code == "ROBOT_STATE_CHANGED_DURING_MOVEIT_OBSERVATION") {
        continue;
      }
      return {std::nullopt, latest_observation->failure.value_or(
                              Failure{FailureCategory::OBSERVATION,
                                      "POST_FAILURE_OBSERVATION_FAILED",
                                      "Unable to observe after cancelling motion",
                                      {}})};
    }
    if (latest_observation->snapshot->fresh && latest_observation->snapshot->arm_stationary) {
      return {*latest_observation->snapshot, std::nullopt};
    }
    std::this_thread::sleep_for(kStationaryPollInterval);
  } while (std::chrono::steady_clock::now() < deadline);
  return {std::nullopt,
          Failure{FailureCategory::POSTCONDITION,
                  "ARM_NOT_QUIESCENT_AFTER_CANCEL",
                  "Motion was cancelled but the robot did not become stationary before the timeout",
                  {{"cancel_succeeded", 1.0}, {"arm_stationary_after_cancel", 0.0}}}};
}

}  // namespace pick_place_common
