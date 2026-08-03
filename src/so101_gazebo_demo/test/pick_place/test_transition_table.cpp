#include <gtest/gtest.h>

#include "so101_gazebo_demo/pick_place/transition_table.hpp"

namespace pick_place = so101_gazebo_demo::pick_place;

TEST(TransitionTable, ContainsEveryActionAndOnlyTerminalStatesAreAbsent)
{
  const auto & entries = pick_place::TransitionTable::entries();
  EXPECT_EQ(28U, entries.size());
  for (const auto & [state, transitions] : entries) {
    EXPECT_TRUE(pick_place::isAction(state) || state == pick_place::State::IDLE ||
                state == pick_place::State::VALIDATION_FAILED);
    EXPECT_NE(pick_place::State::IDLE, transitions.succeeded);
  }
}

TEST(TransitionTable, AttachMoveItFailureSelectsCompleteSafeRecoveryChain)
{
  pick_place::StateMachine state_machine(pick_place::State::ATTACH_MOVEIT);
  const std::vector<pick_place::State> expected{
    pick_place::State::RECOVER_OPEN_GRIPPER,
    pick_place::State::RECOVER_DETACH_GAZEBO,
    pick_place::State::RECOVER_DETACH_MOVEIT,
    pick_place::State::RECOVER_SYNC_WORLD_OBJECT,
    pick_place::State::RECOVER_RETREAT,
    pick_place::State::ERROR,
  };
  EXPECT_EQ(expected.front(), state_machine.advance(pick_place::ActionStatus::FAILED));
  for (std::size_t index = 1; index < expected.size(); ++index) {
    EXPECT_EQ(expected[index], state_machine.advance(pick_place::ActionStatus::SUCCEEDED));
  }
}

TEST(TransitionTable, StableContactAttachesBeforeAnyCarryingLift)
{
  EXPECT_EQ(
    pick_place::State::ATTACH_GAZEBO,
    pick_place::TransitionTable::resolve(
      pick_place::State::WAIT_GRASP_STABLE,
      pick_place::ActionStatus::SUCCEEDED));
}

TEST(TransitionTable, PlacementOpensUnderAttachmentBeforeDetachingAndRetreating)
{
  EXPECT_EQ(pick_place::State::OPEN_GRIPPER,
            pick_place::TransitionTable::resolve(
              pick_place::State::DESCEND_TO_PLACE, pick_place::ActionStatus::SUCCEEDED));
  EXPECT_EQ(pick_place::State::DETACH_GAZEBO,
            pick_place::TransitionTable::resolve(
              pick_place::State::OPEN_GRIPPER, pick_place::ActionStatus::SUCCEEDED));
  EXPECT_EQ(pick_place::State::DETACH_MOVEIT,
            pick_place::TransitionTable::resolve(
              pick_place::State::DETACH_GAZEBO, pick_place::ActionStatus::SUCCEEDED));
  EXPECT_EQ(pick_place::State::SYNC_WORLD_OBJECT,
            pick_place::TransitionTable::resolve(
              pick_place::State::DETACH_MOVEIT, pick_place::ActionStatus::SUCCEEDED));
}

TEST(FailureFormatting, PrintsMessageAndSortedMetricsForRuntimeDiagnosis)
{
  const pick_place::Failure failure{
    pick_place::FailureCategory::GRIPPER,
    "Q6_TARGET_OUT_OF_TOLERANCE",
    "Joint 6 is outside the configured target tolerance",
    {{"expected_q6", 0.795386732}, {"actual_q6", 1.7}}};

  EXPECT_EQ(
    "failure=Q6_TARGET_OUT_OF_TOLERANCE\n"
    "failure_message=Joint 6 is outside the configured target tolerance\n"
    "failure_metrics actual_q6=1.7 expected_q6=0.795386732",
    pick_place::formatFailure(failure));
}
