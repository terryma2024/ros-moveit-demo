#include <gtest/gtest.h>

#include <vector>
#include <type_traits>

#include "pick_place_common/domain_types.hpp"
#include "panda_gazebo_demo/pick_place/domain_types.hpp"
#include "panda_gazebo_demo/pick_place/transition_table.hpp"
#include "panda_gazebo_demo/pick_place/panda_workflow.hpp"

namespace pp = panda_gazebo_demo::pick_place;

static_assert(std::is_same_v<pp::State, pick_place_common::State>);

TEST(PandaWorkflowCharacterization, ForwardAndRecoveryEdgesRemainStable)
{
  const std::vector<pp::State> expected_forward{pp::State::IDLE,
                                                pp::State::PREPARE_OPEN_GRIPPER,
                                                pp::State::MOVE_ABOVE_OBJECT,
                                                pp::State::DESCEND,
                                                pp::State::CLOSE_GRIPPER,
                                                pp::State::ATTACH_GAZEBO,
                                                pp::State::ATTACH_MOVEIT,
                                                pp::State::LIFT,
                                                pp::State::MOVE_ABOVE_PLACE,
                                                pp::State::DESCEND_TO_PLACE,
                                                pp::State::OPEN_GRIPPER,
                                                pp::State::DETACH_GAZEBO,
                                                pp::State::DETACH_MOVEIT,
                                                pp::State::SYNC_WORLD_OBJECT,
                                                pp::State::RETREAT,
                                                pp::State::DONE};
  std::vector<pp::State> actual{pp::State::IDLE};
  for (std::size_t i = 1; i < expected_forward.size(); ++i) {
    actual.push_back(pp::TransitionTable::resolve(actual.back(), pp::ActionStatus::SUCCEEDED));
  }
  EXPECT_EQ(expected_forward, actual);
  EXPECT_EQ(pp::State::RECOVER_RETREAT,
            pp::TransitionTable::resolve(pp::State::MOVE_ABOVE_OBJECT, pp::ActionStatus::FAILED));
  EXPECT_EQ(pp::State::RECOVER_OPEN_GRIPPER,
            pp::TransitionTable::resolve(pp::State::DESCEND, pp::ActionStatus::FAILED));
  EXPECT_EQ(pp::State::RECOVER_LIFT_TO_SAFE_HEIGHT,
            pp::TransitionTable::resolve(pp::State::LIFT, pp::ActionStatus::FAILED));
}

TEST(PandaWorkflowCharacterization, RequestDefaultsRemainStable)
{
  const pp::RunRequest request{};
  EXPECT_EQ(pp::RunMode::DRY_RUN, request.mode);
  EXPECT_FALSE(request.stop_after);
  EXPECT_FALSE(request.resume);
  EXPECT_FALSE(request.fail_at);
  EXPECT_EQ(100U, request.max_state_transitions);
}

TEST(PandaWorkflowCharacterization, CompatibilityTableMatchesEveryWorkflowEdge)
{
  const auto & workflow = pp::pandaWorkflowDefinition();
  for (const auto & [state, edges] : workflow.transitions) {
    EXPECT_EQ(edges.succeeded, pp::TransitionTable::resolve(state, pp::ActionStatus::SUCCEEDED));
    EXPECT_EQ(edges.failed, pp::TransitionTable::resolve(state, pp::ActionStatus::FAILED));
  }
  for (const auto state : workflow.terminal_states) {
    EXPECT_EQ(state, pp::TransitionTable::resolve(state, pp::ActionStatus::SUCCEEDED));
    EXPECT_EQ(state, pp::TransitionTable::resolve(state, pp::ActionStatus::FAILED));
  }
}
