#include <gtest/gtest.h>

#include <set>
#include <string>
#include <type_traits>
#include <vector>

#include "so101_gazebo_demo/pick_place/runner.hpp"

namespace pp = so101_gazebo_demo::pick_place;

TEST(SO101WorkflowCharacterization, UsesCommonDomainTypeAndDeclaresExtendedWorkflow)
{
  static_assert(std::is_same_v<pp::State, pick_place_common::State>);
  const auto & workflow = pp::so101WorkflowDefinition();
  EXPECT_EQ((std::set<pick_place_common::State>{pick_place_common::State::VALIDATION_FAILED}),
            workflow.force_continue_states);
  EXPECT_TRUE(workflow.action_states.count(pick_place_common::State::MICRO_LIFT));
  EXPECT_TRUE(workflow.action_states.count(pick_place_common::State::VERIFY_PHYSICAL_GRASP));
}

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
                                        pp::State::MICRO_LIFT,
                                        pp::State::WAIT_MICRO_LIFT_STABLE,
                                        pp::State::VERIFY_PHYSICAL_GRASP,
                                        pp::State::ATTACH_MOVEIT,
                                        pp::State::LIFT,
                                        pp::State::MOVE_ABOVE_PLACE,
                                        pp::State::DESCEND_TO_PLACE,
                                        pp::State::DETACH_MOVEIT,
                                        pp::State::OPEN_GRIPPER,
                                        pp::State::WAIT_RELEASE_SETTLE,
                                        pp::State::VALIDATE_FINAL_PLACEMENT,
                                        pp::State::SYNC_WORLD_OBJECT,
                                        pp::State::RETREAT,
                                        pp::State::DONE};
  EXPECT_EQ(expected, result.state_trace);
  EXPECT_EQ("MICRO_LIFT", std::string(pp::toString(pp::State::MICRO_LIFT)));
  EXPECT_EQ("VERIFY_PHYSICAL_GRASP", std::string(pp::toString(pp::State::VERIFY_PHYSICAL_GRASP)));
  EXPECT_EQ("VALIDATION_FAILED", std::string(pp::toString(pp::State::VALIDATION_FAILED)));
  const auto & workflow = pp::so101WorkflowDefinition();
  EXPECT_EQ(pp::State::MICRO_LIFT, workflow.transitions.at(pp::State::WAIT_GRASP_STABLE).succeeded);
  EXPECT_EQ(pp::State::VALIDATION_FAILED,
            workflow.transitions.at(pp::State::VERIFY_PHYSICAL_GRASP).failed);
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

TEST(SO101WorkflowCharacterization, HistoricalPositionalRequestAggregateRemainsSupported)
{
  const pp::RunRequest request{
    pp::RunMode::EXECUTE, std::nullopt, true, std::nullopt, 100, true, true};
  EXPECT_TRUE(request.single_step);
  EXPECT_TRUE(request.force_continue);
  EXPECT_FALSE(request.plan_only_state);
}

TEST(SO101WorkflowCharacterization, AttachMoveItFailureContractRemainsStable)
{
  const pp::StateMachineRunner runner;
  pp::RunRequest request;
  request.mode = pp::RunMode::DRY_RUN;
  request.fail_at = pp::State::ATTACH_MOVEIT;
  const auto result = runner.run(request);
  EXPECT_EQ(pp::RunStatus::ERROR, result.status);
  EXPECT_EQ(pp::State::ERROR, result.current_state);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("DRY_RUN_FAILURE_INJECTED", result.failure->code);
  EXPECT_EQ(15U, result.transition_count);
  const std::vector<pp::State> expected{pp::State::IDLE,
                                        pp::State::PREPARE_OPEN_GRIPPER,
                                        pp::State::MOVE_ABOVE_OBJECT,
                                        pp::State::DESCEND,
                                        pp::State::CLOSE_GRIPPER,
                                        pp::State::WAIT_GRASP_STABLE,
                                        pp::State::MICRO_LIFT,
                                        pp::State::WAIT_MICRO_LIFT_STABLE,
                                        pp::State::VERIFY_PHYSICAL_GRASP,
                                        pp::State::ATTACH_MOVEIT,
                                        pp::State::RECOVER_OPEN_GRIPPER,
                                        pp::State::RECOVER_DETACH_GAZEBO,
                                        pp::State::RECOVER_DETACH_MOVEIT,
                                        pp::State::RECOVER_SYNC_WORLD_OBJECT,
                                        pp::State::RECOVER_RETREAT,
                                        pp::State::ERROR};
  EXPECT_EQ(expected, result.state_trace);
}

TEST(SO101WorkflowCharacterization, DeclaresExactPlanOnlyStates)
{
  const auto & workflow = pp::so101WorkflowDefinition();
  const std::set<pp::State> expected{
    pp::State::MOVE_ABOVE_OBJECT, pp::State::DESCEND,          pp::State::LIFT,
    pp::State::MOVE_ABOVE_PLACE,  pp::State::DESCEND_TO_PLACE, pp::State::RETREAT};

  EXPECT_EQ(expected, workflow.plan_only_states);
  for (const auto state : workflow.plan_only_states) {
    EXPECT_TRUE(workflow.action_states.count(state));
    EXPECT_TRUE(workflow.forward_states.count(state));
    EXPECT_FALSE(workflow.terminal_states.count(state));
  }
}
