#include <gtest/gtest.h>

#include <string>
#include <vector>

#include "so101_gazebo_demo/pick_place/runner.hpp"

namespace pp = so101_gazebo_demo::pick_place;

TEST(SO101WorkflowCharacterization, DefaultDryRunTraceAndExtendedStatesRemainStable)
{
  const pp::StateMachineRunner runner;
  const auto result = runner.run({pp::RunMode::DRY_RUN});
  const std::vector<pp::State> expected{pp::State::IDLE,
                                        pp::State::PREPARE_OPEN_GRIPPER,
                                        pp::State::MOVE_ABOVE_OBJECT,
                                        pp::State::DESCEND,
                                        pp::State::CLOSE_GRIPPER,
                                        pp::State::WAIT_GRASP_STABLE,
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
  EXPECT_EQ(expected, result.state_trace);
  EXPECT_EQ("MICRO_LIFT", std::string(pp::toString(pp::State::MICRO_LIFT)));
  EXPECT_EQ("VERIFY_PHYSICAL_GRASP", std::string(pp::toString(pp::State::VERIFY_PHYSICAL_GRASP)));
  EXPECT_EQ("VALIDATION_FAILED", std::string(pp::toString(pp::State::VALIDATION_FAILED)));
}

TEST(SO101WorkflowCharacterization, RequestDefaultsRemainStable)
{
  const pp::RunRequest request{};
  EXPECT_EQ(pp::RunMode::DRY_RUN, request.mode);
  EXPECT_FALSE(request.stop_after);
  EXPECT_FALSE(request.resume);
  EXPECT_FALSE(request.fail_at);
  EXPECT_EQ(100U, request.max_state_transitions);
  EXPECT_FALSE(request.single_step);
  EXPECT_FALSE(request.force_continue);
}

TEST(SO101WorkflowCharacterization, AttachMoveItFailureContractRemainsStable)
{
  const pp::StateMachineRunner runner;
  const auto result =
    runner.run({pp::RunMode::DRY_RUN, std::nullopt, false, pp::State::ATTACH_MOVEIT});
  EXPECT_EQ(pp::RunStatus::ERROR, result.status);
  EXPECT_EQ(pp::State::ERROR, result.current_state);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("DRY_RUN_FAILURE_INJECTED", result.failure->code);
  EXPECT_EQ(13U, result.transition_count);
  const std::vector<pp::State> expected{pp::State::IDLE,
                                        pp::State::PREPARE_OPEN_GRIPPER,
                                        pp::State::MOVE_ABOVE_OBJECT,
                                        pp::State::DESCEND,
                                        pp::State::CLOSE_GRIPPER,
                                        pp::State::WAIT_GRASP_STABLE,
                                        pp::State::ATTACH_GAZEBO,
                                        pp::State::ATTACH_MOVEIT,
                                        pp::State::RECOVER_OPEN_GRIPPER,
                                        pp::State::RECOVER_DETACH_GAZEBO,
                                        pp::State::RECOVER_DETACH_MOVEIT,
                                        pp::State::RECOVER_SYNC_WORLD_OBJECT,
                                        pp::State::RECOVER_RETREAT,
                                        pp::State::ERROR};
  EXPECT_EQ(expected, result.state_trace);
}
