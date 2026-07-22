#include <gtest/gtest.h>

#include <memory>

#include "panda_gazebo_demo/pick_place/checkpoint.hpp"
#include "panda_gazebo_demo/pick_place/runner.hpp"

namespace pick_place = panda_gazebo_demo::pick_place;

namespace
{

class FakePlanner final : public pick_place::IStatePlanner
{
public:
  pick_place::PlanResult plan(pick_place::State state) override
  {
    ++calls;
    last_state = state;
    auto artifact = std::make_shared<pick_place::PlanArtifact>();
    artifact->trajectory_points = 3;
    return {{pick_place::ActionStatus::SUCCEEDED, std::nullopt}, artifact};
  }

  int calls{0};
  pick_place::State last_state{pick_place::State::ERROR};
};

class FakeExecutor final : public pick_place::IStateExecutor
{
public:
  pick_place::ActionResult execute(
    pick_place::State state, std::shared_ptr<const pick_place::PlanArtifact>) override
  {
    ++calls;
    last_state = state;
    return {pick_place::ActionStatus::SUCCEEDED, std::nullopt};
  }

  pick_place::ActionResult cancel() override
  {
    return {pick_place::ActionStatus::SUCCEEDED, std::nullopt};
  }

  int calls{0};
  pick_place::State last_state{pick_place::State::ERROR};
};

class FakeObserver final : public pick_place::IWorldObserver
{
public:
  pick_place::ObservationResult observe() override
  {
    ++calls;
    return {calls == 1 || !after_snapshot ? snapshot : *after_snapshot, std::nullopt};
  }

  pick_place::WorldSnapshot snapshot{
    std::chrono::steady_clock::now(), true, true, true, false,
    {0.3, 0.0, 0.987, 1.0, 0.0, 0.0, 0.0}, {},
    {{"table", {}}, {"coke", {0.3, 0.0, 0.6, 0.0, 0.0, 0.0, 1.0}}}};
  std::optional<pick_place::WorldSnapshot> after_snapshot;
  int calls{0};
};

class FakeCheckpointStore final : public pick_place::ICheckpointStore
{
public:
  std::optional<pick_place::Failure> commit(const pick_place::Checkpoint & value) override
  {
    checkpoint = value;
    ++calls;
    return failure;
  }

  std::optional<pick_place::Checkpoint> checkpoint;
  std::optional<pick_place::Failure> failure;
  int calls{0};
};

}  // namespace

TEST(TransitionTable, SeparatesBusinessStateFromRunStatus)
{
  EXPECT_FALSE(pick_place::stateFromString("PLAN_ONLY_COMPLETE").has_value());
  EXPECT_FALSE(pick_place::stateFromString("MOVE_ABOVE_OBJECT_EXECUTED").has_value());
  EXPECT_STREQ("PLAN_ONLY_COMPLETE",
    pick_place::toString(pick_place::RunStatus::PLAN_ONLY_COMPLETE));
}

TEST(TransitionTable, RoutesSuccessAndFailureEdges)
{
  pick_place::StateMachine machine;
  EXPECT_EQ(pick_place::State::MOVE_ABOVE_OBJECT,
    machine.advance(pick_place::ActionStatus::SUCCEEDED));
  EXPECT_EQ(pick_place::State::ERROR, machine.advance(pick_place::ActionStatus::FAILED));
}

TEST(Runner, DryRunCompletesAndNeverNeedsAnActionRegistry)
{
  pick_place::StateActionRegistry actions;
  pick_place::TransitionContractRegistry contracts;
  const pick_place::StateMachineRunner runner(actions, contracts);

  const auto result = runner.run({pick_place::RunMode::DRY_RUN, std::nullopt, false, std::nullopt,
        100});
  EXPECT_EQ(pick_place::RunStatus::DONE, result.status);
  EXPECT_EQ(pick_place::State::DONE, result.current_state);
  EXPECT_FALSE(result.failure.has_value());
}

TEST(Runner, DryRunFailureFollowsTheRecoveryPathAndReportsTheInjection)
{
  pick_place::StateActionRegistry actions;
  pick_place::TransitionContractRegistry contracts;
  const pick_place::StateMachineRunner runner(actions, contracts);

  const auto result = runner.run({pick_place::RunMode::DRY_RUN, std::nullopt, false,
        pick_place::State::DESCEND, 100});
  EXPECT_EQ(pick_place::RunStatus::ERROR, result.status);
  EXPECT_EQ(pick_place::State::ERROR, result.current_state);
  ASSERT_TRUE(result.failure.has_value());
  EXPECT_EQ("DRY_RUN_FAILURE_INJECTED", result.failure->code);
}

TEST(Runner, DryRunFailureTakesPriorityOverStopAfter)
{
  pick_place::StateActionRegistry actions;
  pick_place::TransitionContractRegistry contracts;
  const pick_place::StateMachineRunner runner(actions, contracts);

  const auto result = runner.run({pick_place::RunMode::DRY_RUN, pick_place::State::DESCEND, false,
        pick_place::State::DESCEND, 100});
  EXPECT_EQ(pick_place::RunStatus::ERROR, result.status);
  ASSERT_TRUE(result.failure.has_value());
  EXPECT_EQ("DRY_RUN_FAILURE_INJECTED", result.failure->code);
}

TEST(Runner, PlanOnlyUsesExactlyOnePlannerAndDoesNotAdvanceBusinessState)
{
  pick_place::StateActionRegistry actions;
  auto planner = std::make_shared<FakePlanner>();
  actions.registerPlanner(pick_place::State::MOVE_ABOVE_OBJECT, planner);
  pick_place::TransitionContractRegistry contracts;
  const pick_place::StateMachineRunner runner(actions, contracts);

  const auto result = runner.run({pick_place::RunMode::PLAN_ONLY, std::nullopt, false, std::nullopt,
        100});
  EXPECT_EQ(pick_place::RunStatus::PLAN_ONLY_COMPLETE, result.status);
  EXPECT_EQ(pick_place::State::MOVE_ABOVE_OBJECT, result.current_state);
  EXPECT_EQ(pick_place::State::DESCEND, *result.next_state);
  EXPECT_EQ(1, planner->calls);
  EXPECT_EQ(pick_place::State::MOVE_ABOVE_OBJECT, planner->last_state);
}

TEST(Runner, RejectsExecuteOutsideTheSingleApprovedScope)
{
  pick_place::StateActionRegistry actions;
  pick_place::TransitionContractRegistry contracts;
  const pick_place::StateMachineRunner runner(actions, contracts);

  const auto result = runner.run({pick_place::RunMode::EXECUTE, std::nullopt, false, std::nullopt,
        100});
  ASSERT_TRUE(result.failure.has_value());
  EXPECT_EQ("EXECUTE_SCOPE_REJECTED", result.failure->code);
}

TEST(Runner, ExecutesOnlyMoveAboveAndCommitsAfterPostValidation)
{
  pick_place::StateActionRegistry actions;
  auto planner = std::make_shared<FakePlanner>();
  auto executor = std::make_shared<FakeExecutor>();
  actions.registerPlanner(pick_place::State::MOVE_ABOVE_OBJECT, planner);
  actions.registerExecutor(pick_place::State::MOVE_ABOVE_OBJECT, executor);
  pick_place::TransitionContractRegistry contracts;
  contracts.registerContract(
    {pick_place::State::MOVE_ABOVE_OBJECT, pick_place::State::DESCEND},
    std::make_shared<pick_place::MoveAboveObjectContract>(
      pick_place::Pose3d{0.3, 0.0, 0.987, 1.0, 0.0, 0.0, 0.0},
      std::vector<std::string>{"table", "coke"}, 0.02, 0.01));
  FakeObserver observer;
  observer.snapshot.gripper_open = false;
  FakeCheckpointStore checkpoints;
  const pick_place::StateMachineRunner runner(actions, contracts, &observer, &checkpoints);

  const auto result = runner.run({pick_place::RunMode::EXECUTE,
        pick_place::State::MOVE_ABOVE_OBJECT, false, std::nullopt, 100});
  EXPECT_EQ(pick_place::RunStatus::CHECKPOINT_COMPLETE, result.status);
  EXPECT_EQ(pick_place::State::MOVE_ABOVE_OBJECT, result.current_state);
  EXPECT_EQ(pick_place::State::DESCEND, *result.next_state);
  EXPECT_EQ(1, executor->calls);
  EXPECT_EQ(2, observer.calls);
  ASSERT_TRUE(checkpoints.checkpoint.has_value());
  EXPECT_EQ(pick_place::State::DESCEND, checkpoints.checkpoint->next_state);
}

TEST(Runner, DoesNotCommitWhenPostValidationFails)
{
  pick_place::StateActionRegistry actions;
  auto planner = std::make_shared<FakePlanner>();
  auto executor = std::make_shared<FakeExecutor>();
  actions.registerPlanner(pick_place::State::MOVE_ABOVE_OBJECT, planner);
  actions.registerExecutor(pick_place::State::MOVE_ABOVE_OBJECT, executor);
  pick_place::TransitionContractRegistry contracts;
  contracts.registerContract(
    {pick_place::State::MOVE_ABOVE_OBJECT, pick_place::State::DESCEND},
    std::make_shared<pick_place::MoveAboveObjectContract>(
      pick_place::Pose3d{0.3, 0.0, 0.987, 1.0, 0.0, 0.0, 0.0},
      std::vector<std::string>{"table", "coke"}, 0.02, 0.01));
  FakeObserver observer;
  observer.after_snapshot = observer.snapshot;
  observer.after_snapshot->tcp_pose_world.x = 0.5;
  FakeCheckpointStore checkpoints;
  const pick_place::StateMachineRunner runner(actions, contracts, &observer, &checkpoints);

  const auto result = runner.run({pick_place::RunMode::EXECUTE,
        pick_place::State::MOVE_ABOVE_OBJECT, false, std::nullopt, 100});
  ASSERT_TRUE(result.failure.has_value());
  EXPECT_EQ("TCP_OUTSIDE_PREGRASP_TOLERANCE", result.failure->code);
  EXPECT_EQ(1, executor->calls);
  EXPECT_EQ(0, checkpoints.calls);
}

TEST(Runner, RejectsFailureInjectionOutsideDryRun)
{
  pick_place::StateActionRegistry actions;
  pick_place::TransitionContractRegistry contracts;
  const pick_place::StateMachineRunner runner(actions, contracts);

  const auto result = runner.run({pick_place::RunMode::PLAN_ONLY, std::nullopt, false,
        pick_place::State::MOVE_ABOVE_OBJECT, 100});
  ASSERT_TRUE(result.failure.has_value());
  EXPECT_EQ("FAIL_AT_MODE_MISMATCH", result.failure->code);
}

TEST(TransitionContracts, MissingExecuteContractFailsClosed)
{
  pick_place::TransitionContractRegistry contracts;
  pick_place::TransitionTable table;
  const auto failure = contracts.validateExecuteCoverage(table);
  ASSERT_TRUE(failure.has_value());
  EXPECT_EQ("MISSING_TRANSITION_CONTRACT", failure->code);
}
