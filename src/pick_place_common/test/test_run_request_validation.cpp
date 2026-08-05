#include <gtest/gtest.h>

#include <type_traits>

#include "pick_place_common/run_request_validation.hpp"

namespace pp = pick_place_common;

static_assert(std::is_aggregate_v<pick_place_common::RunRequest>);

namespace
{
pp::WorkflowDefinition workflowFixture()
{
  pp::WorkflowDefinition workflow;
  workflow.transitions[pp::State::IDLE] = {pp::State::PREPARE_OPEN_GRIPPER, pp::State::ERROR};
  workflow.transitions[pp::State::PREPARE_OPEN_GRIPPER] = {pp::State::MOVE_ABOVE_OBJECT,
                                                           pp::State::ERROR};
  workflow.transitions[pp::State::MOVE_ABOVE_OBJECT] = {pp::State::DESCEND, pp::State::ERROR};
  workflow.transitions[pp::State::DESCEND] = {pp::State::DONE, pp::State::ERROR};
  workflow.action_states = {pp::State::PREPARE_OPEN_GRIPPER, pp::State::MOVE_ABOVE_OBJECT,
                            pp::State::DESCEND};
  workflow.forward_states = {pp::State::IDLE, pp::State::PREPARE_OPEN_GRIPPER,
                             pp::State::MOVE_ABOVE_OBJECT, pp::State::DESCEND, pp::State::DONE};
  workflow.terminal_states = {pp::State::DONE, pp::State::ERROR};
  workflow.plan_only_states = {pp::State::MOVE_ABOVE_OBJECT, pp::State::DESCEND};
  return workflow;
}

void expectFailureCode(const pp::WorkflowDefinition & workflow, const pp::RunRequest & request,
                       const char * expected_code)
{
  const auto failure = pp::validateRunRequest(workflow, request);
  ASSERT_TRUE(failure);
  EXPECT_EQ(expected_code, failure->code);
}
}  // namespace

TEST(RunRequestValidation, RejectsInvalidRequestsWithStableCodes)
{
  const auto workflow = workflowFixture();

  pp::RunRequest missing_target;
  missing_target.mode = pp::RunMode::PLAN_ONLY;
  expectFailureCode(workflow, missing_target, "PLAN_ONLY_STATE_REQUIRED");

  auto disallowed = missing_target;
  disallowed.plan_only_state = pp::State::CLOSE_GRIPPER;
  expectFailureCode(workflow, disallowed, "PLAN_ONLY_STATE_NOT_ALLOWED");

  auto unreachable_workflow = workflow;
  unreachable_workflow.plan_only_states.insert(pp::State::LIFT);
  auto unreachable = missing_target;
  unreachable.plan_only_state = pp::State::LIFT;
  expectFailureCode(unreachable_workflow, unreachable, "PLAN_ONLY_STATE_UNREACHABLE");

  pp::RunRequest execute_with_target;
  execute_with_target.mode = pp::RunMode::EXECUTE;
  execute_with_target.plan_only_state = pp::State::MOVE_ABOVE_OBJECT;
  expectFailureCode(workflow, execute_with_target, "PLAN_ONLY_ARGUMENT_CONFLICT");

  pp::RunRequest dry_run_with_target;
  dry_run_with_target.plan_only_state = pp::State::MOVE_ABOVE_OBJECT;
  expectFailureCode(workflow, dry_run_with_target, "PLAN_ONLY_ARGUMENT_CONFLICT");

  auto stop_after = missing_target;
  stop_after.plan_only_state = pp::State::MOVE_ABOVE_OBJECT;
  stop_after.stop_after = pp::State::MOVE_ABOVE_OBJECT;
  expectFailureCode(workflow, stop_after, "PLAN_ONLY_ARGUMENT_CONFLICT");

  auto single_step = missing_target;
  single_step.plan_only_state = pp::State::MOVE_ABOVE_OBJECT;
  single_step.single_step = true;
  expectFailureCode(workflow, single_step, "PLAN_ONLY_ARGUMENT_CONFLICT");

  pp::RunRequest zero_transitions;
  zero_transitions.max_state_transitions = 0;
  expectFailureCode(workflow, zero_transitions, "INVALID_MAX_TRANSITIONS");

  pp::RunRequest fail_at_execute;
  fail_at_execute.mode = pp::RunMode::EXECUTE;
  fail_at_execute.fail_at = pp::State::DESCEND;
  expectFailureCode(workflow, fail_at_execute, "FAIL_AT_MODE_MISMATCH");

  pp::RunRequest invalid_force_continue;
  invalid_force_continue.force_continue = true;
  expectFailureCode(workflow, invalid_force_continue, "FORCE_CONTINUE_REQUEST_INVALID");

  pp::RunRequest terminal_stop;
  terminal_stop.stop_after = pp::State::DONE;
  expectFailureCode(workflow, terminal_stop, "STOP_AFTER_STATE_NOT_ACTION");

  pp::RunRequest idle_stop;
  idle_stop.stop_after = pp::State::IDLE;
  expectFailureCode(workflow, idle_stop, "STOP_AFTER_STATE_NOT_ACTION");

  pp::RunRequest recovery_fail;
  recovery_fail.fail_at = pp::State::RECOVER_RETREAT;
  expectFailureCode(workflow, recovery_fail, "FAIL_AT_STATE_NOT_FORWARD_ACTION");

  pp::RunRequest terminal_fail;
  terminal_fail.fail_at = pp::State::ERROR;
  expectFailureCode(workflow, terminal_fail, "FAIL_AT_STATE_NOT_FORWARD_ACTION");
}

TEST(RunRequestValidation, ComparesForwardPathPositions)
{
  const auto workflow = workflowFixture();
  EXPECT_EQ(
    pp::ForwardPathRelation::UPSTREAM,
    pp::compareForwardPathPosition(workflow, pp::State::PREPARE_OPEN_GRIPPER, pp::State::DESCEND));
  EXPECT_EQ(pp::ForwardPathRelation::SAME,
            pp::compareForwardPathPosition(workflow, pp::State::MOVE_ABOVE_OBJECT,
                                           pp::State::MOVE_ABOVE_OBJECT));
  EXPECT_EQ(
    pp::ForwardPathRelation::DOWNSTREAM,
    pp::compareForwardPathPosition(workflow, pp::State::DESCEND, pp::State::MOVE_ABOVE_OBJECT));
  EXPECT_EQ(
    pp::ForwardPathRelation::UNREACHABLE,
    pp::compareForwardPathPosition(workflow, pp::State::RECOVER_RETREAT, pp::State::DESCEND));
}

TEST(RunRequestValidation, AcceptsValidPlanOnlyRequest)
{
  const auto workflow = workflowFixture();
  pp::RunRequest request;
  request.mode = pp::RunMode::PLAN_ONLY;
  request.plan_only_state = pp::State::DESCEND;
  EXPECT_FALSE(pp::validateRunRequest(workflow, request));
}
