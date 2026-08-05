#include <gtest/gtest.h>

#include <algorithm>
#include <memory>
#include <string>
#include <utility>
#include <vector>

#include "pick_place_common/runner.hpp"

namespace pp = pick_place_common;

namespace
{
struct Scenario
{
  std::vector<std::string> events;
  pp::WorldSnapshot world;
  int observer_calls{};
  int planner_calls{};
  int executor_calls{};
  std::string target_failure_stage;
  bool recovery_execute_failure{};
};

class Observer final : public pp::IWorldObserver
{
public:
  explicit Observer(Scenario & scenario) : scenario_(scenario) {}

  pp::ObservationResult observe() override
  {
    ++scenario_.observer_calls;
    scenario_.events.emplace_back("observe");
    return {scenario_.world, std::nullopt};
  }

private:
  Scenario & scenario_;
};

class Contract final : public pp::TransitionContractRegistry::ITransitionContract
{
public:
  Contract(Scenario & scenario, pp::State state) : scenario_(scenario), state_(state) {}

  pp::ValidationResult validatePrecondition(const pp::WorldSnapshot &) const override
  {
    scenario_.events.emplace_back(std::string("precondition ") + pp::toString(state_));
    if (state_ == pp::State::MOVE_ABOVE_OBJECT &&
        scenario_.target_failure_stage == "precondition") {
      return {false,
              {pp::Failure{pp::FailureCategory::PRECONDITION,
                           "TARGET_PRECONDITION_FAILED",
                           "Target precondition failed",
                           {}}},
              {}};
    }
    return {true, {}, {}};
  }

  pp::ValidationResult validate(const pp::WorldSnapshot &, const pp::WorldSnapshot &,
                                const pp::ActionResult &) const override
  {
    scenario_.events.emplace_back(std::string("postcondition ") + pp::toString(state_));
    return {true, {}, {}};
  }

private:
  Scenario & scenario_;
  pp::State state_;
};

class Planner final : public pp::IStatePlanner
{
public:
  Planner(Scenario & scenario, pp::State state) : scenario_(scenario), state_(state) {}

  pp::PlanResult plan(pp::State, pp::State, const pp::ObservationResult &) override
  {
    ++scenario_.planner_calls;
    scenario_.events.emplace_back(std::string("plan ") + pp::toString(state_));
    if (state_ == pp::State::MOVE_ABOVE_OBJECT && scenario_.target_failure_stage == "planning") {
      return {{pp::ActionStatus::FAILED, pp::Failure{pp::FailureCategory::PLANNING,
                                                     "TARGET_PLAN_FAILED",
                                                     "Target planning failed",
                                                     {}}},
              nullptr};
    }
    auto artifact = std::make_shared<pp::PlanArtifact>();
    artifact->trajectory_points = 1;
    return {{pp::ActionStatus::SUCCEEDED, std::nullopt}, artifact};
  }

private:
  Scenario & scenario_;
  pp::State state_;
};

class PlanValidator final : public pp::IPlanValidator
{
public:
  PlanValidator(Scenario & scenario, pp::State state) : scenario_(scenario), state_(state) {}

  pp::ValidationResult validate(pp::State, const pp::WorldSnapshot &,
                                const pp::PlanArtifact &) const override
  {
    scenario_.events.emplace_back(std::string("validate-plan ") + pp::toString(state_));
    if (state_ == pp::State::MOVE_ABOVE_OBJECT &&
        scenario_.target_failure_stage == "plan_validation") {
      return {false,
              {pp::Failure{pp::FailureCategory::PLAN_VALIDATION,
                           "TARGET_PLAN_VALIDATION_FAILED",
                           "Target plan validation failed",
                           {}}},
              {}};
    }
    return {true, {}, {}};
  }

private:
  Scenario & scenario_;
  pp::State state_;
};

class Executor final : public pp::IStateExecutor
{
public:
  Executor(Scenario & scenario, pp::State state) : scenario_(scenario), state_(state) {}

  pp::ActionResult execute(const pp::ExecutionContext &) override
  {
    ++scenario_.executor_calls;
    scenario_.events.emplace_back(std::string("execute ") + pp::toString(state_));
    if (state_ == pp::State::RECOVER_RETREAT && scenario_.recovery_execute_failure) {
      return {pp::ActionStatus::FAILED, pp::Failure{pp::FailureCategory::EXECUTION,
                                                    "RECOVERY_EXECUTION_FAILED",
                                                    "Recovery execution failed",
                                                    {}}};
    }
    return {pp::ActionStatus::SUCCEEDED, std::nullopt};
  }

  pp::ActionResult cancel() override
  {
    scenario_.events.emplace_back(std::string("cancel ") + pp::toString(state_));
    return {pp::ActionStatus::SUCCEEDED, std::nullopt};
  }

private:
  Scenario & scenario_;
  pp::State state_;
};

class Store final : public pp::ICheckpointStore
{
public:
  explicit Store(Scenario & scenario) : scenario_(scenario) {}

  std::optional<pp::Failure> commit(const pp::Checkpoint & checkpoint) override
  {
    checkpoints.push_back(checkpoint);
    scenario_.events.emplace_back(std::string("checkpoint ") +
                                  pp::toString(checkpoint.last_completed_state));
    return std::nullopt;
  }

  pp::CheckpointLoadResult loadLatestCompatible() override
  {
    ++load_calls;
    return {loaded, std::nullopt};
  }

  std::vector<pp::Checkpoint> checkpoints;
  std::optional<pp::Checkpoint> loaded;
  int load_calls{};

private:
  Scenario & scenario_;
};

class ResumePolicy final : public pp::IResumeValidationPolicy
{
public:
  pp::ValidationResult validateBoundary(const pp::Checkpoint &, const pp::WorldSnapshot &,
                                        double) const override
  {
    return {true, {}, {}};
  }

  std::string fingerprintMismatchCode() const override
  {
    return "FINGERPRINT_MISMATCH";
  }
};

class RecoveryPolicy final : public pp::IRecoveryPolicy
{
public:
  pp::RecoveryRoute select(pp::State, const pp::Failure &, const pp::WorldSnapshot &) const override
  {
    return {pp::State::RECOVER_RETREAT, std::nullopt};
  }

  bool canSkipRecoveryAction(pp::State, const pp::Failure &, pp::State,
                             const pp::WorldSnapshot &) const override
  {
    return skip_recovery_action;
  }

  bool skip_recovery_action{false};
};

pp::WorkflowDefinition workflow()
{
  pp::WorkflowDefinition result;
  result.transitions[pp::State::IDLE] = {pp::State::PREPARE_OPEN_GRIPPER, pp::State::ERROR};
  result.transitions[pp::State::PREPARE_OPEN_GRIPPER] = {pp::State::MOVE_ABOVE_OBJECT,
                                                         pp::State::ERROR};
  result.transitions[pp::State::MOVE_ABOVE_OBJECT] = {pp::State::DESCEND,
                                                      pp::State::RECOVER_RETREAT};
  result.transitions[pp::State::DESCEND] = {pp::State::DONE, pp::State::RECOVER_RETREAT};
  result.transitions[pp::State::RECOVER_RETREAT] = {pp::State::ERROR, pp::State::ERROR};
  result.action_states = {pp::State::PREPARE_OPEN_GRIPPER, pp::State::MOVE_ABOVE_OBJECT,
                          pp::State::DESCEND, pp::State::RECOVER_RETREAT};
  result.forward_states = {pp::State::IDLE, pp::State::PREPARE_OPEN_GRIPPER,
                           pp::State::MOVE_ABOVE_OBJECT, pp::State::DESCEND, pp::State::DONE};
  result.terminal_states = {pp::State::DONE, pp::State::ERROR};
  result.plan_only_states = {pp::State::MOVE_ABOVE_OBJECT, pp::State::DESCEND};
  return result;
}

struct RegistrationOptions
{
  bool observer{true};
  bool store{true};
  bool resume_validator{true};
  bool recovery_policy{true};
  bool prepare_executor{true};
  bool prepare_contract{true};
  bool target_executor{true};
  bool target_planner{true};
  bool target_validator{true};
  bool target_contract{true};
};

class Harness
{
public:
  explicit Harness(RegistrationOptions options = {}) : observer(scenario), store(scenario)
  {
    scenario.world.fresh = true;
    scenario.world.arm_stationary = true;
    scenario.world.gazebo_task_object_stationary = true;
    scenario.world.simulation_session_id = "session";
    if (options.prepare_executor) {
      actions.registerExecutor(
        pp::State::PREPARE_OPEN_GRIPPER,
        std::make_shared<Executor>(scenario, pp::State::PREPARE_OPEN_GRIPPER));
    }
    if (options.prepare_contract) {
      contracts.registerContract(
        {pp::State::PREPARE_OPEN_GRIPPER, pp::State::MOVE_ABOVE_OBJECT},
        std::make_shared<Contract>(scenario, pp::State::PREPARE_OPEN_GRIPPER));
    }
    registerTarget(pp::State::MOVE_ABOVE_OBJECT, pp::State::DESCEND, options);
    registerTarget(pp::State::DESCEND, pp::State::DONE, options);
    actions.registerExecutor(pp::State::RECOVER_RETREAT,
                             std::make_shared<Executor>(scenario, pp::State::RECOVER_RETREAT));
    contracts.registerContract({pp::State::RECOVER_RETREAT, pp::State::ERROR},
                               std::make_shared<Contract>(scenario, pp::State::RECOVER_RETREAT));
    resume_validator = std::make_unique<pp::CommonResumeValidator>(
      "fingerprint", "session", std::make_shared<ResumePolicy>());
    runner = std::make_unique<pp::StateMachineRunner>(
      definition, actions, contracts, options.observer ? &observer : nullptr,
      options.store ? &store : nullptr, options.resume_validator ? resume_validator.get() : nullptr,
      nullptr, &validators, options.recovery_policy ? &recovery : nullptr);
  }

  pp::RunResult run(pp::State target)
  {
    pp::RunRequest request;
    request.mode = pp::RunMode::PLAN_ONLY;
    request.plan_only_state = target;
    return runner->run(request);
  }

  void clearCalls()
  {
    scenario.events.clear();
    scenario.observer_calls = 0;
    scenario.planner_calls = 0;
    scenario.executor_calls = 0;
    store.checkpoints.clear();
    store.load_calls = 0;
  }

  Scenario scenario;
  pp::WorkflowDefinition definition{workflow()};
  Observer observer;
  Store store;
  pp::StateActionRegistry actions;
  pp::TransitionContractRegistry contracts;
  pp::PlanValidatorRegistry validators;
  RecoveryPolicy recovery;
  std::unique_ptr<pp::CommonResumeValidator> resume_validator;
  std::unique_ptr<pp::StateMachineRunner> runner;

private:
  void registerTarget(pp::State state, pp::State next, const RegistrationOptions & options)
  {
    if (options.target_executor) {
      actions.registerExecutor(state, std::make_shared<Executor>(scenario, state));
    }
    if (options.target_planner) {
      actions.registerPlanner(state, std::make_shared<Planner>(scenario, state));
    }
    if (options.target_validator) {
      validators.registerValidator(state, std::make_shared<PlanValidator>(scenario, state));
    }
    if (options.target_contract) {
      contracts.registerContract({state, next}, std::make_shared<Contract>(scenario, state));
    }
  }
};

void expectZeroCalls(const Harness & harness)
{
  EXPECT_EQ(0, harness.scenario.observer_calls);
  EXPECT_EQ(0, harness.scenario.planner_calls);
  EXPECT_EQ(0, harness.scenario.executor_calls);
  EXPECT_TRUE(harness.store.checkpoints.empty());
}

pp::Checkpoint forwardCheckpoint(pp::State completed, pp::State next)
{
  pp::Checkpoint checkpoint;
  checkpoint.sequence = 7;
  checkpoint.source_mode = pp::RunMode::EXECUTE;
  checkpoint.phase = pp::CheckpointPhase::FORWARD;
  checkpoint.last_completed_state = completed;
  checkpoint.next_state = next;
  checkpoint.configuration_fingerprint = "fingerprint";
  checkpoint.simulation_session_id = "session";
  return checkpoint;
}

pp::RunRequest resumeRequest(pp::State target)
{
  pp::RunRequest request;
  request.mode = pp::RunMode::PLAN_ONLY;
  request.plan_only_state = target;
  request.resume = true;
  return request;
}

pp::WorkflowDefinition forceContinueWorkflow()
{
  pp::WorkflowDefinition workflow;
  workflow.transitions[pp::State::IDLE] = {pp::State::VERIFY_PHYSICAL_GRASP, pp::State::ERROR};
  workflow.transitions[pp::State::VERIFY_PHYSICAL_GRASP] = {pp::State::ATTACH_GAZEBO,
                                                            pp::State::VALIDATION_FAILED};
  workflow.transitions[pp::State::VALIDATION_FAILED] = {pp::State::ATTACH_GAZEBO,
                                                        pp::State::VALIDATION_FAILED};
  workflow.transitions[pp::State::ATTACH_GAZEBO] = {pp::State::DONE, pp::State::RECOVER_RETREAT};
  workflow.transitions[pp::State::RECOVER_RETREAT] = {pp::State::ERROR, pp::State::ERROR};
  workflow.action_states = {pp::State::VERIFY_PHYSICAL_GRASP, pp::State::ATTACH_GAZEBO,
                            pp::State::RECOVER_RETREAT};
  workflow.forward_states = {pp::State::IDLE, pp::State::VERIFY_PHYSICAL_GRASP,
                             pp::State::VALIDATION_FAILED, pp::State::ATTACH_GAZEBO,
                             pp::State::DONE};
  workflow.terminal_states = {pp::State::DONE, pp::State::ERROR};
  workflow.force_continue_states = {pp::State::VALIDATION_FAILED};
  return workflow;
}

void expectTargetFailureRecovers(const std::string & stage, const std::string & expected_code)
{
  Harness harness;
  harness.scenario.target_failure_stage = stage;
  const auto result = harness.run(pp::State::MOVE_ABOVE_OBJECT);

  ASSERT_EQ(pp::RunStatus::ERROR, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ(expected_code, result.failure->code);
  EXPECT_EQ(0, std::count(harness.scenario.events.begin(), harness.scenario.events.end(),
                          "execute MOVE_ABOVE_OBJECT"));
  EXPECT_EQ(1, std::count(harness.scenario.events.begin(), harness.scenario.events.end(),
                          "cancel MOVE_ABOVE_OBJECT"));
  EXPECT_EQ(1, std::count(harness.scenario.events.begin(), harness.scenario.events.end(),
                          "execute RECOVER_RETREAT"));
  ASSERT_GE(harness.store.checkpoints.size(), 2U);
  EXPECT_EQ(pp::CheckpointPhase::RECOVERY, harness.store.checkpoints[1].phase);
  ASSERT_TRUE(harness.store.checkpoints[1].original_failure);
  EXPECT_EQ(expected_code, harness.store.checkpoints[1].original_failure->code);
}
}  // namespace

TEST(RunToPlanOnly, ExecutesPredecessorsThenPlansTargetWithoutExecutingIt)
{
  Harness harness;
  const auto result = harness.run(pp::State::MOVE_ABOVE_OBJECT);

  EXPECT_EQ(pp::RunStatus::PLAN_ONLY_COMPLETE, result.status);
  EXPECT_EQ((std::vector<std::string>{
              "observe", "precondition PREPARE_OPEN_GRIPPER", "execute PREPARE_OPEN_GRIPPER",
              "observe", "postcondition PREPARE_OPEN_GRIPPER", "checkpoint PREPARE_OPEN_GRIPPER",
              "observe", "precondition MOVE_ABOVE_OBJECT", "plan MOVE_ABOVE_OBJECT",
              "validate-plan MOVE_ABOVE_OBJECT"}),
            harness.scenario.events);
  EXPECT_EQ(harness.scenario.events.end(),
            std::find(harness.scenario.events.begin(), harness.scenario.events.end(),
                      "execute MOVE_ABOVE_OBJECT"));
}

TEST(RunToPlanOnly, DeepTargetExecutesEveryUpstreamActionExactlyOnce)
{
  Harness harness;
  const auto result = harness.run(pp::State::DESCEND);

  EXPECT_EQ(pp::RunStatus::PLAN_ONLY_COMPLETE, result.status);
  EXPECT_EQ(2, harness.scenario.executor_calls);
  EXPECT_EQ(2, harness.scenario.planner_calls);
  EXPECT_EQ(1, std::count(harness.scenario.events.begin(), harness.scenario.events.end(),
                          "execute PREPARE_OPEN_GRIPPER"));
  EXPECT_EQ(1, std::count(harness.scenario.events.begin(), harness.scenario.events.end(),
                          "execute MOVE_ABOVE_OBJECT"));
  EXPECT_EQ(0, std::count(harness.scenario.events.begin(), harness.scenario.events.end(),
                          "execute DESCEND"));
}

TEST(RunToPlanOnly, SuccessLeavesCheckpointAtTargetEntry)
{
  Harness harness;
  const auto result = harness.run(pp::State::MOVE_ABOVE_OBJECT);

  ASSERT_EQ(pp::RunStatus::PLAN_ONLY_COMPLETE, result.status);
  ASSERT_EQ(1U, harness.store.checkpoints.size());
  const auto & checkpoint = harness.store.checkpoints.back();
  EXPECT_EQ(pp::RunMode::EXECUTE, checkpoint.source_mode);
  EXPECT_EQ(pp::CheckpointPhase::FORWARD, checkpoint.phase);
  EXPECT_EQ(pp::State::PREPARE_OPEN_GRIPPER, checkpoint.last_completed_state);
  EXPECT_EQ(pp::State::MOVE_ABOVE_OBJECT, checkpoint.next_state);
}

TEST(RunToPlanOnly, ResultTraceAndTransitionCountDescribeOnlyRealTransitions)
{
  Harness harness;
  const auto result = harness.run(pp::State::MOVE_ABOVE_OBJECT);

  EXPECT_EQ(pp::RunStatus::PLAN_ONLY_COMPLETE, result.status);
  EXPECT_EQ(pp::State::MOVE_ABOVE_OBJECT, result.current_state);
  EXPECT_EQ(pp::State::DESCEND, result.next_state);
  EXPECT_EQ(2U, result.transition_count);
  EXPECT_EQ((std::vector<pp::State>{pp::State::IDLE, pp::State::PREPARE_OPEN_GRIPPER,
                                    pp::State::MOVE_ABOVE_OBJECT}),
            result.state_trace);
}

TEST(RunToPlanOnly, RequestErrorsHaveZeroSideEffects)
{
  Harness harness;
  std::vector<std::pair<pp::RunRequest, std::string>> cases;

  pp::RunRequest missing;
  missing.mode = pp::RunMode::PLAN_ONLY;
  cases.emplace_back(missing, "PLAN_ONLY_STATE_REQUIRED");

  auto disallowed = missing;
  disallowed.plan_only_state = pp::State::RECOVER_RETREAT;
  cases.emplace_back(disallowed, "PLAN_ONLY_STATE_NOT_ALLOWED");

  auto conflict = missing;
  conflict.plan_only_state = pp::State::MOVE_ABOVE_OBJECT;
  conflict.stop_after = pp::State::MOVE_ABOVE_OBJECT;
  cases.emplace_back(conflict, "PLAN_ONLY_ARGUMENT_CONFLICT");

  pp::RunRequest execute_target;
  execute_target.mode = pp::RunMode::EXECUTE;
  execute_target.plan_only_state = pp::State::MOVE_ABOVE_OBJECT;
  cases.emplace_back(execute_target, "PLAN_ONLY_ARGUMENT_CONFLICT");

  for (const auto & [request, code] : cases) {
    harness.clearCalls();
    const auto result = harness.runner->run(request);
    ASSERT_TRUE(result.failure);
    EXPECT_EQ(code, result.failure->code);
    expectZeroCalls(harness);
  }
}

TEST(RunToPlanOnly, MissingInfrastructureFailsBeforeAnyCalls)
{
  std::vector<std::pair<RegistrationOptions, std::string>> cases;
  RegistrationOptions options;
  options.observer = false;
  cases.emplace_back(options, "EXECUTE_INFRASTRUCTURE_MISSING");
  options = {};
  options.store = false;
  cases.emplace_back(options, "EXECUTE_INFRASTRUCTURE_MISSING");
  options = {};
  options.resume_validator = false;
  cases.emplace_back(options, "EXECUTE_INFRASTRUCTURE_MISSING");
  options = {};
  options.recovery_policy = false;
  cases.emplace_back(options, "RECOVERY_POLICY_MISSING");
  options = {};
  options.prepare_executor = false;
  cases.emplace_back(options, "EXECUTE_ACTION_NOT_REGISTERED");
  options = {};
  options.prepare_contract = false;
  cases.emplace_back(options, "MISSING_TRANSITION_CONTRACT");
  options = {};
  options.target_executor = false;
  cases.emplace_back(options, "EXECUTE_ACTION_NOT_REGISTERED");
  options = {};
  options.target_planner = false;
  cases.emplace_back(options, "PLANNER_NOT_REGISTERED");
  options = {};
  options.target_validator = false;
  cases.emplace_back(options, "PLAN_VALIDATOR_NOT_REGISTERED");
  options = {};
  options.target_contract = false;
  cases.emplace_back(options, "MISSING_TRANSITION_CONTRACT");

  for (const auto & [options, code] : cases) {
    Harness harness(options);
    const auto result = harness.run(pp::State::MOVE_ABOVE_OBJECT);
    ASSERT_TRUE(result.failure);
    EXPECT_EQ(code, result.failure->code);
    expectZeroCalls(harness);
  }
}

TEST(RunToPlanOnlyResume, SameTargetCheckpointValidatesThenPlansWithoutExecuting)
{
  Harness harness;
  harness.store.loaded =
    forwardCheckpoint(pp::State::PREPARE_OPEN_GRIPPER, pp::State::MOVE_ABOVE_OBJECT);

  const auto result = harness.runner->run(resumeRequest(pp::State::MOVE_ABOVE_OBJECT));

  EXPECT_EQ(pp::RunStatus::PLAN_ONLY_COMPLETE, result.status);
  EXPECT_EQ(1, harness.store.load_calls);
  EXPECT_EQ(1, harness.scenario.planner_calls);
  EXPECT_EQ(0, harness.scenario.executor_calls);
  EXPECT_TRUE(harness.store.checkpoints.empty());
}

TEST(RunToPlanOnlyResume, UpstreamCheckpointExecutesRemainderThenPlansTarget)
{
  Harness harness;
  harness.store.loaded =
    forwardCheckpoint(pp::State::PREPARE_OPEN_GRIPPER, pp::State::MOVE_ABOVE_OBJECT);

  const auto result = harness.runner->run(resumeRequest(pp::State::DESCEND));

  EXPECT_EQ(pp::RunStatus::PLAN_ONLY_COMPLETE, result.status);
  EXPECT_EQ(1, harness.scenario.executor_calls);
  EXPECT_EQ(2, harness.scenario.planner_calls);
  ASSERT_EQ(1U, harness.store.checkpoints.size());
  EXPECT_EQ(pp::State::MOVE_ABOVE_OBJECT, harness.store.checkpoints.back().last_completed_state);
  EXPECT_EQ(pp::State::DESCEND, harness.store.checkpoints.back().next_state);
  EXPECT_EQ(0, std::count(harness.scenario.events.begin(), harness.scenario.events.end(),
                          "execute DESCEND"));
}

TEST(RunToPlanOnlyResume, PassedTargetFailsBeforeObservation)
{
  Harness harness;
  harness.store.loaded = forwardCheckpoint(pp::State::MOVE_ABOVE_OBJECT, pp::State::DESCEND);

  const auto result = harness.runner->run(resumeRequest(pp::State::MOVE_ABOVE_OBJECT));

  ASSERT_TRUE(result.failure);
  EXPECT_EQ("PLAN_ONLY_TARGET_ALREADY_PASSED", result.failure->code);
  EXPECT_EQ(1, harness.store.load_calls);
  expectZeroCalls(harness);
}

TEST(RunToPlanOnlyResume, RecoveryCheckpointFailsBeforeObservation)
{
  Harness harness;
  auto checkpoint = forwardCheckpoint(pp::State::MOVE_ABOVE_OBJECT, pp::State::RECOVER_RETREAT);
  checkpoint.phase = pp::CheckpointPhase::RECOVERY;
  checkpoint.failed_state = pp::State::MOVE_ABOVE_OBJECT;
  checkpoint.original_failure =
    pp::Failure{pp::FailureCategory::PLANNING, "ORIGINAL_FAILURE", "Original failure", {}};
  harness.store.loaded = checkpoint;

  const auto result = harness.runner->run(resumeRequest(pp::State::DESCEND));

  ASSERT_TRUE(result.failure);
  EXPECT_EQ("PLAN_ONLY_RECOVERY_RESUME_UNSUPPORTED", result.failure->code);
  EXPECT_EQ(1, harness.store.load_calls);
  expectZeroCalls(harness);
}

TEST(RunToPlanOnly, RecoveryResumeSkipsSelectedActionAndPreservesOriginalFailure)
{
  Harness harness;
  harness.recovery.skip_recovery_action = true;
  auto checkpoint = forwardCheckpoint(pp::State::MOVE_ABOVE_OBJECT, pp::State::RECOVER_RETREAT);
  checkpoint.phase = pp::CheckpointPhase::RECOVERY;
  checkpoint.failed_state = pp::State::MOVE_ABOVE_OBJECT;
  checkpoint.original_failure = pp::Failure{pp::FailureCategory::PLAN_VALIDATION,
                                             "ORIGINAL_FAILURE", "Original failure",
                                             {{"plan_only_target_not_executed", 1.0}}};
  harness.store.loaded = checkpoint;

  pp::RunRequest request;
  request.mode = pp::RunMode::EXECUTE;
  request.resume = true;
  const auto result = harness.runner->run(request);

  ASSERT_EQ(pp::RunStatus::ERROR, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ(checkpoint.original_failure->category, result.failure->category);
  EXPECT_EQ(checkpoint.original_failure->code, result.failure->code);
  EXPECT_EQ(checkpoint.original_failure->message, result.failure->message);
  EXPECT_EQ(checkpoint.original_failure->metrics, result.failure->metrics);
  EXPECT_EQ(0, harness.scenario.executor_calls);
  EXPECT_EQ((std::vector<pp::State>{pp::State::RECOVER_RETREAT, pp::State::ERROR}),
            result.state_trace);
}

TEST(RunToPlanOnlyResume, WorldSessionAndFingerprintMismatchRemainFailClosed)
{
  Harness harness;
  auto checkpoint =
    forwardCheckpoint(pp::State::PREPARE_OPEN_GRIPPER, pp::State::MOVE_ABOVE_OBJECT);
  checkpoint.configuration_fingerprint = "wrong";
  harness.store.loaded = checkpoint;
  auto result = harness.runner->run(resumeRequest(pp::State::MOVE_ABOVE_OBJECT));
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("FINGERPRINT_MISMATCH", result.failure->code);

  harness.clearCalls();
  checkpoint.configuration_fingerprint = "fingerprint";
  checkpoint.simulation_session_id = "wrong";
  harness.store.loaded = checkpoint;
  result = harness.runner->run(resumeRequest(pp::State::MOVE_ABOVE_OBJECT));
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("RESUME_SIMULATION_SESSION_MISMATCH", result.failure->code);

  harness.clearCalls();
  checkpoint.simulation_session_id = "session";
  harness.store.loaded = checkpoint;
  harness.scenario.world.simulation_session_id = "wrong";
  result = harness.runner->run(resumeRequest(pp::State::MOVE_ABOVE_OBJECT));
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("RESUME_SIMULATION_SESSION_MISMATCH", result.failure->code);
}

TEST(ForceContinue, PassiveExecuteResumePreservesValidationPause)
{
  Harness harness;
  harness.definition = forceContinueWorkflow();
  harness.actions.registerExecutor(
    pp::State::ATTACH_GAZEBO,
    std::make_shared<Executor>(harness.scenario, pp::State::ATTACH_GAZEBO));
  harness.contracts.registerContract(
    {pp::State::ATTACH_GAZEBO, pp::State::DONE},
    std::make_shared<Contract>(harness.scenario, pp::State::ATTACH_GAZEBO));
  auto checkpoint =
    forwardCheckpoint(pp::State::VERIFY_PHYSICAL_GRASP, pp::State::VALIDATION_FAILED);
  checkpoint.failed_state = pp::State::VERIFY_PHYSICAL_GRASP;
  checkpoint.original_failure = pp::Failure{pp::FailureCategory::POSTCONDITION,
                                            "PHYSICAL_GRASP_FOLLOW_RATIO",
                                            "Physical grasp validation failed",
                                            {}};
  harness.store.loaded = checkpoint;

  pp::RunRequest request;
  request.mode = pp::RunMode::EXECUTE;
  request.resume = true;
  const auto result = harness.runner->run(request);

  EXPECT_EQ(pp::RunStatus::CHECKPOINT_COMPLETE, result.status);
  EXPECT_EQ(pp::State::VALIDATION_FAILED, result.current_state);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("PHYSICAL_GRASP_FOLLOW_RATIO", result.failure->code);
  EXPECT_EQ(0, harness.scenario.executor_calls);
  EXPECT_TRUE(harness.store.checkpoints.empty());
}

TEST(ForceContinue, ValidSingleStepOverrideExecutesOnlyGazeboAttach)
{
  Harness harness;
  harness.definition = forceContinueWorkflow();
  harness.actions.registerExecutor(
    pp::State::ATTACH_GAZEBO,
    std::make_shared<Executor>(harness.scenario, pp::State::ATTACH_GAZEBO));
  harness.contracts.registerContract(
    {pp::State::VALIDATION_FAILED, pp::State::ATTACH_GAZEBO},
    std::make_shared<Contract>(harness.scenario, pp::State::VALIDATION_FAILED));
  harness.contracts.registerContract(
    {pp::State::ATTACH_GAZEBO, pp::State::DONE},
    std::make_shared<Contract>(harness.scenario, pp::State::ATTACH_GAZEBO));
  auto checkpoint =
    forwardCheckpoint(pp::State::VERIFY_PHYSICAL_GRASP, pp::State::VALIDATION_FAILED);
  checkpoint.failed_state = pp::State::VERIFY_PHYSICAL_GRASP;
  checkpoint.original_failure = pp::Failure{pp::FailureCategory::POSTCONDITION,
                                            "PHYSICAL_GRASP_FOLLOW_RATIO",
                                            "Physical grasp validation failed",
                                            {}};
  harness.store.loaded = checkpoint;

  pp::RunRequest request;
  request.mode = pp::RunMode::EXECUTE;
  request.resume = true;
  request.force_continue = true;
  request.single_step = true;
  const auto result = harness.runner->run(request);

  EXPECT_EQ(pp::RunStatus::CHECKPOINT_COMPLETE, result.status);
  EXPECT_EQ(pp::State::ATTACH_GAZEBO, result.current_state);
  EXPECT_EQ(pp::State::DONE, result.next_state);
  EXPECT_EQ((std::vector<pp::State>{pp::State::VALIDATION_FAILED,
                                    pp::State::ATTACH_GAZEBO,
                                    pp::State::DONE}),
            result.state_trace);
  EXPECT_EQ(2U, result.transition_count);
  EXPECT_EQ(1, harness.scenario.executor_calls);
}

TEST(ForceContinue, RejectsNormalForwardCheckpointWithoutSideEffects)
{
  Harness harness;
  harness.definition = forceContinueWorkflow();
  harness.actions.registerExecutor(
    pp::State::ATTACH_GAZEBO,
    std::make_shared<Executor>(harness.scenario, pp::State::ATTACH_GAZEBO));
  harness.contracts.registerContract(
    {pp::State::VERIFY_PHYSICAL_GRASP, pp::State::ATTACH_GAZEBO},
    std::make_shared<Contract>(harness.scenario, pp::State::VERIFY_PHYSICAL_GRASP));
  harness.contracts.registerContract(
    {pp::State::ATTACH_GAZEBO, pp::State::DONE},
    std::make_shared<Contract>(harness.scenario, pp::State::ATTACH_GAZEBO));
  harness.store.loaded =
    forwardCheckpoint(pp::State::VERIFY_PHYSICAL_GRASP, pp::State::ATTACH_GAZEBO);

  pp::RunRequest request;
  request.mode = pp::RunMode::EXECUTE;
  request.resume = true;
  request.force_continue = true;
  const auto result = harness.runner->run(request);

  ASSERT_TRUE(result.failure);
  EXPECT_EQ("FORCE_CONTINUE_STATE_MISMATCH", result.failure->code);
  EXPECT_EQ(0, harness.scenario.executor_calls);
  EXPECT_TRUE(harness.store.checkpoints.empty());
}

TEST(RunToPlanOnlyFailure, TargetPreconditionFailureRecoversWithoutExecutingTarget)
{
  expectTargetFailureRecovers("precondition", "TARGET_PRECONDITION_FAILED");
}

TEST(RunToPlanOnlyFailure, TargetPlanningFailureRecoversWithoutExecutingTarget)
{
  expectTargetFailureRecovers("planning", "TARGET_PLAN_FAILED");
}

TEST(RunToPlanOnlyFailure, TargetPlanValidationFailureRecoversWithoutExecutingTarget)
{
  expectTargetFailureRecovers("plan_validation", "TARGET_PLAN_VALIDATION_FAILED");
}

TEST(RunToPlanOnlyFailure, RecoveryFailureRetainsOriginalFailure)
{
  Harness harness;
  harness.scenario.target_failure_stage = "planning";
  harness.scenario.recovery_execute_failure = true;

  const auto result = harness.run(pp::State::MOVE_ABOVE_OBJECT);

  ASSERT_EQ(pp::RunStatus::ERROR, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("RECOVERY_EXECUTION_FAILED", result.failure->code);
  EXPECT_NE(std::string::npos, result.failure->message.find("TARGET_PLAN_FAILED"));
  EXPECT_EQ(0, std::count(harness.scenario.events.begin(), harness.scenario.events.end(),
                          "execute MOVE_ABOVE_OBJECT"));
}
