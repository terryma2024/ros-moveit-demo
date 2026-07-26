#include <gtest/gtest.h>

#include "so101_gazebo_demo/pick_place/transition_table.hpp"

namespace pick_place = so101_gazebo_demo::pick_place;

TEST(TransitionTable, ContainsEveryActionAndOnlyTerminalStatesAreAbsent)
{
  const auto & entries = pick_place::TransitionTable::entries();
  EXPECT_EQ(23U, entries.size());
  for (const auto & [state, transitions] : entries) {
    EXPECT_TRUE(pick_place::isAction(state) || state == pick_place::State::IDLE);
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
