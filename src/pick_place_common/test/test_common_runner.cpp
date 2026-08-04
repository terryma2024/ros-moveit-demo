#include <gtest/gtest.h>
#include <memory>
#include <string>
#include <vector>
#include "pick_place_common/runner.hpp"
namespace pp = pick_place_common;
namespace
{
struct Scenario
{
  std::vector<std::string> events;
  pp::WorldSnapshot world;
};
class Observer final : public pp::IWorldObserver
{
public:
  explicit Observer(Scenario & s) : s_(s)
  {
    s_.world.fresh = true;
    s_.world.arm_stationary = true;
  }
  pp::ObservationResult observe() override
  {
    s_.events.push_back("observe");
    return {s_.world, {}};
  }

private:
  Scenario & s_;
};
class Contract final : public pp::TransitionContractRegistry::ITransitionContract
{
public:
  explicit Contract(Scenario & s) : s_(s) {}
  pp::ValidationResult validatePrecondition(const pp::WorldSnapshot &) const override
  {
    s_.events.push_back("precondition:MOVE_ABOVE_OBJECT");
    return {true, {}, {}};
  }
  pp::ValidationResult validate(const pp::WorldSnapshot &, const pp::WorldSnapshot &,
                                const pp::ActionResult &) const override
  {
    s_.events.push_back("transition-validate:MOVE_ABOVE_OBJECT");
    return {true, {}, {}};
  }

private:
  Scenario & s_;
};
class CountingDecorator final : public pp::ITransitionValidationDecorator
{
public:
  mutable int pre_calls{};
  mutable int post_calls{};
  mutable int resume_calls{};
  pp::ValidationResult decoratePrecondition(pp::TransitionKey, const pp::WorldSnapshot &,
                                            pp::ValidationResult result) const override
  {
    ++pre_calls;
    result.metrics["decorated"] = 1.0;
    for (auto & failure : result.failures)
      failure.metrics["decorated"] = 1.0;
    return result;
  }
  pp::ValidationResult decoratePostcondition(pp::TransitionKey, const pp::WorldSnapshot &,
                                             const pp::WorldSnapshot &, const pp::ActionResult &,
                                             pp::ValidationResult result) const override
  {
    ++post_calls;
    result.metrics["decorated"] = 1.0;
    for (auto & failure : result.failures)
      failure.metrics["decorated"] = 1.0;
    return result;
  }
  pp::ValidationResult decorateResume(pp::TransitionKey, const pp::WorldSnapshot &,
                                      const pp::WorldSnapshot &,
                                      pp::ValidationResult result) const override
  {
    ++resume_calls;
    result.metrics["decorated"] = 1.0;
    for (auto & failure : result.failures)
      failure.metrics["decorated"] = 1.0;
    return result;
  }
};
class Planner final : public pp::IStatePlanner
{
public:
  explicit Planner(Scenario & s) : s_(s) {}
  pp::PlanResult plan(pp::State, pp::State, const pp::ObservationResult &) override
  {
    s_.events.push_back("plan:MOVE_ABOVE_OBJECT");
    auto a = std::make_shared<pp::PlanArtifact>();
    a->trajectory_points = 1;
    return {{pp::ActionStatus::SUCCEEDED, {}}, a};
  }

private:
  Scenario & s_;
};
class Validator final : public pp::IPlanValidator
{
public:
  explicit Validator(Scenario & s) : s_(s) {}
  pp::ValidationResult validate(pp::State, const pp::WorldSnapshot &,
                                const pp::PlanArtifact &) const override
  {
    s_.events.push_back("plan-validate:MOVE_ABOVE_OBJECT");
    return {true, {}, {}};
  }

private:
  Scenario & s_;
};
class Executor final : public pp::IStateExecutor
{
public:
  explicit Executor(Scenario & s) : s_(s) {}
  pp::ActionResult execute(const pp::ExecutionContext &) override
  {
    s_.events.push_back("execute:MOVE_ABOVE_OBJECT");
    return {pp::ActionStatus::SUCCEEDED, {}};
  }
  pp::ActionResult cancel() override
  {
    s_.events.push_back("cancel");
    return {pp::ActionStatus::SUCCEEDED, {}};
  }

private:
  Scenario & s_;
};
class Store final : public pp::ICheckpointStore
{
public:
  explicit Store(Scenario & s) : s_(s) {}
  std::optional<pp::Failure> commit(const pp::Checkpoint &) override
  {
    s_.events.push_back("checkpoint:MOVE_ABOVE_OBJECT");
    return {};
  }
  pp::CheckpointLoadResult loadLatestCompatible() override
  {
    return {};
  }

private:
  Scenario & s_;
};
pp::WorkflowDefinition workflow()
{
  pp::WorkflowDefinition w;
  w.transitions[pp::State::IDLE] = {pp::State::MOVE_ABOVE_OBJECT, pp::State::ERROR};
  w.transitions[pp::State::MOVE_ABOVE_OBJECT] = {pp::State::DONE, pp::State::ERROR};
  w.action_states = {pp::State::MOVE_ABOVE_OBJECT};
  w.forward_states = {pp::State::IDLE, pp::State::MOVE_ABOVE_OBJECT, pp::State::DONE};
  w.terminal_states = {pp::State::DONE, pp::State::ERROR};
  return w;
}
}  // namespace
TEST(CommonRunner, ExecutePreservesBoundaryOrder)
{
  Scenario s;
  Observer observer(s);
  Store store(s);
  pp::StateActionRegistry actions;
  actions.registerPlanner(pp::State::MOVE_ABOVE_OBJECT, std::make_shared<Planner>(s));
  actions.registerExecutor(pp::State::MOVE_ABOVE_OBJECT, std::make_shared<Executor>(s));
  pp::TransitionContractRegistry contracts;
  contracts.registerContract({pp::State::MOVE_ABOVE_OBJECT, pp::State::DONE},
                             std::make_shared<Contract>(s));
  pp::PlanValidatorRegistry validators;
  validators.registerValidator(pp::State::MOVE_ABOVE_OBJECT, std::make_shared<Validator>(s));
  const auto w = workflow();
  pp::StateMachineRunner runner(w, actions, contracts, &observer, &store, nullptr, nullptr,
                                &validators);
  const auto result = runner.run({pp::RunMode::EXECUTE});
  EXPECT_EQ(pp::RunStatus::DONE, result.status);
  EXPECT_EQ((std::vector<std::string>{
              "observe", "precondition:MOVE_ABOVE_OBJECT", "plan:MOVE_ABOVE_OBJECT",
              "plan-validate:MOVE_ABOVE_OBJECT", "execute:MOVE_ABOVE_OBJECT", "observe",
              "transition-validate:MOVE_ABOVE_OBJECT", "checkpoint:MOVE_ABOVE_OBJECT"}),
            s.events);
}
TEST(CommonRunner, PlanOnlyDoesNotExecute)
{
  Scenario s;
  Observer observer(s);
  pp::StateActionRegistry actions;
  actions.registerPlanner(pp::State::MOVE_ABOVE_OBJECT, std::make_shared<Planner>(s));
  actions.registerExecutor(pp::State::MOVE_ABOVE_OBJECT, std::make_shared<Executor>(s));
  pp::TransitionContractRegistry contracts;
  contracts.registerContract({pp::State::MOVE_ABOVE_OBJECT, pp::State::DONE},
                             std::make_shared<Contract>(s));
  pp::PlanValidatorRegistry validators;
  validators.registerValidator(pp::State::MOVE_ABOVE_OBJECT, std::make_shared<Validator>(s));
  const auto w = workflow();
  pp::StateMachineRunner runner(w, actions, contracts, &observer, nullptr, nullptr, nullptr,
                                &validators);
  const auto result = runner.run({pp::RunMode::PLAN_ONLY});
  EXPECT_EQ(pp::RunStatus::PLAN_ONLY_COMPLETE, result.status);
  EXPECT_EQ(s.events.end(),
            std::find(s.events.begin(), s.events.end(), "execute:MOVE_ABOVE_OBJECT"));
}
TEST(CommonRunner, DryRunAndBudgetAreDefinitionDriven)
{
  pp::StateActionRegistry actions;
  pp::TransitionContractRegistry contracts;
  const auto w = workflow();
  pp::StateMachineRunner runner(w, actions, contracts);
  const auto ok = runner.run({pp::RunMode::DRY_RUN});
  EXPECT_EQ(
    (std::vector<pp::State>{pp::State::IDLE, pp::State::MOVE_ABOVE_OBJECT, pp::State::DONE}),
    ok.state_trace);
  auto request = pp::RunRequest{};
  request.max_state_transitions = 1;
  EXPECT_EQ("STATE_TRANSITION_BUDGET_EXHAUSTED", runner.run(request).failure->code);
}

TEST(CommonRunner, RegistryDecoratorRunsExactlyOnceOnEveryValidationPath)
{
  Scenario scenario;
  auto decorator = std::make_shared<CountingDecorator>();
  pp::TransitionContractRegistry contracts(true, true, decorator);
  contracts.registerContract({pp::State::MOVE_ABOVE_OBJECT, pp::State::DONE},
                             std::make_shared<Contract>(scenario));
  pp::WorldSnapshot world;
  const pp::TransitionKey key{pp::State::MOVE_ABOVE_OBJECT, pp::State::DONE};

  const auto precondition = contracts.validatePrecondition(key, world);
  const auto postcondition =
    contracts.validate(key, world, world, {pp::ActionStatus::SUCCEEDED, {}});
  const auto resume = contracts.validateResume(key, world, world);

  EXPECT_TRUE(precondition.ok);
  EXPECT_TRUE(postcondition.ok);
  EXPECT_TRUE(resume.ok);
  EXPECT_EQ(1, decorator->pre_calls);
  EXPECT_EQ(1, decorator->post_calls);
  EXPECT_EQ(1, decorator->resume_calls);
  EXPECT_EQ(1.0, precondition.metrics.at("decorated"));
  EXPECT_EQ(1.0, postcondition.metrics.at("decorated"));
  EXPECT_EQ(1.0, resume.metrics.at("decorated"));
}

TEST(CommonRunner, RegistryDecoratorCopiesMetricsIntoFailuresWithoutInventingFailures)
{
  auto decorator = std::make_shared<CountingDecorator>();
  pp::TransitionContractRegistry contracts(true, true, decorator);
  pp::WorldSnapshot world;
  const pp::TransitionKey missing{pp::State::MOVE_ABOVE_OBJECT, pp::State::DONE};

  const auto precondition = contracts.validatePrecondition(missing, world);
  const auto postcondition =
    contracts.validate(missing, world, world, {pp::ActionStatus::FAILED, {}});
  const auto resume = contracts.validateResume(missing, world, world);

  for (const auto * result : {&precondition, &postcondition, &resume}) {
    ASSERT_FALSE(result->ok);
    ASSERT_EQ(1U, result->failures.size());
    EXPECT_EQ(1.0, result->metrics.at("decorated"));
    EXPECT_EQ(1.0, result->failures.front().metrics.at("decorated"));
  }
}
