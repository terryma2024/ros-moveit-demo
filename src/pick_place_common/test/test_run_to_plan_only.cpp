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
    return {};
  }

  std::vector<pp::Checkpoint> checkpoints;

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
    return {std::nullopt,
            pp::Failure{pp::FailureCategory::INTERNAL, "NO_TEST_ROUTE", "No test route", {}}};
  }
};

pp::WorkflowDefinition workflow()
{
  pp::WorkflowDefinition result;
  result.transitions[pp::State::IDLE] = {pp::State::PREPARE_OPEN_GRIPPER, pp::State::ERROR};
  result.transitions[pp::State::PREPARE_OPEN_GRIPPER] = {pp::State::MOVE_ABOVE_OBJECT,
                                                         pp::State::ERROR};
  result.transitions[pp::State::MOVE_ABOVE_OBJECT] = {pp::State::DESCEND, pp::State::ERROR};
  result.transitions[pp::State::DESCEND] = {pp::State::DONE, pp::State::ERROR};
  result.action_states = {pp::State::PREPARE_OPEN_GRIPPER, pp::State::MOVE_ABOVE_OBJECT,
                          pp::State::DESCEND};
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
