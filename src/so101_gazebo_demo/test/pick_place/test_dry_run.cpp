#include <gtest/gtest.h>

#include "so101_gazebo_demo/pick_place/runner.hpp"

namespace pick_place = so101_gazebo_demo::pick_place;

TEST(DryRun, NormalWorkflowEndsDone)
{
  pick_place::StateMachineRunner runner;
  const auto result = runner.run({pick_place::RunMode::DRY_RUN});
  EXPECT_EQ(pick_place::RunStatus::DONE, result.status);
  EXPECT_EQ(pick_place::State::DONE, result.current_state);
  EXPECT_EQ(15U, result.transition_count);
}

TEST(DryRun, AttachMoveItFailureRunsCompleteRecoveryAndEndsError)
{
  pick_place::StateMachineRunner runner;
  const auto result = runner.run({pick_place::RunMode::DRY_RUN, std::nullopt, false,
                                  pick_place::State::ATTACH_MOVEIT});
  EXPECT_EQ(pick_place::RunStatus::ERROR, result.status);
  EXPECT_EQ(pick_place::State::ERROR, result.current_state);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("DRY_RUN_FAILURE_INJECTED", result.failure->code);
  EXPECT_EQ(12U, result.transition_count);
}

TEST(DryRun, StopAfterPersistsTheNextBoundary)
{
  pick_place::StateMachineRunner runner;
  const auto result = runner.run({pick_place::RunMode::DRY_RUN,
                                  pick_place::State::DESCEND});
  EXPECT_EQ(pick_place::RunStatus::CHECKPOINT_COMPLETE, result.status);
  EXPECT_EQ(pick_place::State::CLOSE_GRIPPER, result.current_state);
  ASSERT_TRUE(result.next_state);
  EXPECT_EQ(pick_place::State::CLOSE_GRIPPER, *result.next_state);
}

TEST(UnsafeModes, FailClosedWithoutAdapters)
{
  pick_place::StateMachineRunner runner;
  for (const auto mode : {pick_place::RunMode::PLAN_ONLY, pick_place::RunMode::EXECUTE}) {
    const auto result = runner.run({mode});
    EXPECT_EQ(pick_place::RunStatus::ERROR, result.status);
    ASSERT_TRUE(result.failure);
    EXPECT_EQ("UNSAFE_ADAPTERS_NOT_REGISTERED", result.failure->code);
  }
}
