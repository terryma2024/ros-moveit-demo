#include <gtest/gtest.h>

#include "pick_place_common/workflow_definition.hpp"

namespace pp = pick_place_common;

namespace
{
pp::WorkflowDefinition validPlanOnlyWorkflow()
{
  pp::WorkflowDefinition workflow;
  workflow.transitions[pp::State::IDLE] = {pp::State::PREPARE_OPEN_GRIPPER, pp::State::ERROR};
  workflow.transitions[pp::State::PREPARE_OPEN_GRIPPER] = {pp::State::MOVE_ABOVE_OBJECT,
                                                           pp::State::ERROR};
  workflow.transitions[pp::State::MOVE_ABOVE_OBJECT] = {pp::State::DONE, pp::State::ERROR};
  workflow.action_states = {pp::State::PREPARE_OPEN_GRIPPER, pp::State::MOVE_ABOVE_OBJECT};
  workflow.forward_states = {pp::State::IDLE, pp::State::PREPARE_OPEN_GRIPPER,
                             pp::State::MOVE_ABOVE_OBJECT, pp::State::DONE};
  workflow.terminal_states = {pp::State::DONE, pp::State::ERROR};
  return workflow;
}
}  // namespace

TEST(WorkflowDefinition, NewPhysicalOutcomeStatesRoundTripWithoutGlobalWorkflowMembership)
{
  const auto workflow = validPlanOnlyWorkflow();
  for (const auto state :
       {pp::State::WAIT_RELEASE_SETTLE, pp::State::VALIDATE_FINAL_PLACEMENT}) {
    const auto parsed = pp::stateFromString(pp::toString(state));
    ASSERT_TRUE(parsed);
    EXPECT_EQ(state, *parsed);
    EXPECT_FALSE(workflow.transitions.count(state));
    EXPECT_FALSE(workflow.action_states.count(state));
    EXPECT_FALSE(workflow.forward_states.count(state));
  }
}

TEST(WorkflowDefinition, RejectsMissingTransitionAndUnknownTarget)
{
  pp::WorkflowDefinition missing;
  missing.initial_state = pp::State::IDLE;
  missing.action_states = {pp::State::PREPARE_OPEN_GRIPPER};
  missing.terminal_states = {pp::State::DONE, pp::State::ERROR};
  auto failure = pp::validateWorkflowDefinition(missing);
  ASSERT_TRUE(failure);
  EXPECT_EQ("WORKFLOW_TRANSITION_MISSING", failure->code);

  missing.transitions[pp::State::IDLE] = {pp::State::PREPARE_OPEN_GRIPPER, pp::State::ERROR};
  failure = pp::validateWorkflowDefinition(missing);
  ASSERT_TRUE(failure);
  EXPECT_EQ("WORKFLOW_TRANSITION_TARGET_UNKNOWN", failure->code);
}

TEST(WorkflowDefinition, RejectsTerminalActionAndInvalidForceContinue)
{
  pp::WorkflowDefinition workflow;
  workflow.initial_state = pp::State::IDLE;
  workflow.transitions[pp::State::IDLE] = {pp::State::DONE, pp::State::ERROR};
  workflow.terminal_states = {pp::State::DONE, pp::State::ERROR};
  workflow.action_states = {pp::State::DONE};
  auto failure = pp::validateWorkflowDefinition(workflow);
  ASSERT_TRUE(failure);
  EXPECT_EQ("WORKFLOW_TERMINAL_ACTION_OVERLAP", failure->code);

  workflow.action_states.clear();
  workflow.force_continue_states = {pp::State::VALIDATION_FAILED};
  failure = pp::validateWorkflowDefinition(workflow);
  ASSERT_TRUE(failure);
  EXPECT_EQ("WORKFLOW_FORCE_CONTINUE_STATE_UNKNOWN", failure->code);
}

TEST(WorkflowDefinition, ValidDefinitionDrivesStateMachine)
{
  pp::WorkflowDefinition workflow;
  workflow.initial_state = pp::State::IDLE;
  workflow.transitions[pp::State::IDLE] = {pp::State::PREPARE_OPEN_GRIPPER, pp::State::ERROR};
  workflow.transitions[pp::State::PREPARE_OPEN_GRIPPER] = {pp::State::DONE, pp::State::ERROR};
  workflow.action_states = {pp::State::PREPARE_OPEN_GRIPPER};
  workflow.forward_states = {pp::State::IDLE, pp::State::PREPARE_OPEN_GRIPPER, pp::State::DONE};
  workflow.terminal_states = {pp::State::DONE, pp::State::ERROR};
  EXPECT_FALSE(pp::validateWorkflowDefinition(workflow));
  pp::StateMachine machine(workflow, pp::State::IDLE);
  EXPECT_EQ(pp::State::PREPARE_OPEN_GRIPPER, machine.advance(pp::ActionStatus::SUCCEEDED));
  EXPECT_EQ(pp::State::DONE, machine.advance(pp::ActionStatus::SUCCEEDED));
}

TEST(WorkflowDefinition, ResolvesBothEdgesTerminalSelfLoopsAndUnknownStates)
{
  pp::WorkflowDefinition workflow;
  workflow.transitions[pp::State::IDLE] = {pp::State::DONE, pp::State::ERROR};
  workflow.terminal_states = {pp::State::DONE, pp::State::ERROR};

  EXPECT_EQ(pp::State::DONE,
            pp::resolveTransition(workflow, pp::State::IDLE, pp::ActionStatus::SUCCEEDED));
  EXPECT_EQ(pp::State::ERROR,
            pp::resolveTransition(workflow, pp::State::IDLE, pp::ActionStatus::FAILED));
  EXPECT_EQ(pp::State::DONE,
            pp::resolveTransition(workflow, pp::State::DONE, pp::ActionStatus::FAILED));
  EXPECT_EQ(pp::State::ERROR,
            pp::resolveTransition(workflow, pp::State::ERROR, pp::ActionStatus::SUCCEEDED));
  EXPECT_EQ(pp::State::ERROR, pp::resolveTransition(workflow, pp::State::MOVE_ABOVE_OBJECT,
                                                    pp::ActionStatus::SUCCEEDED));
}

TEST(WorkflowDefinition, AcceptsReachableActionPlanOnlyState)
{
  auto workflow = validPlanOnlyWorkflow();
  workflow.plan_only_states = {pp::State::MOVE_ABOVE_OBJECT};
  EXPECT_FALSE(pp::validateWorkflowDefinition(workflow));
}

TEST(WorkflowDefinition, RejectsInvalidPlanOnlyDeclarations)
{
  auto terminal = validPlanOnlyWorkflow();
  terminal.plan_only_states = {pp::State::DONE};
  ASSERT_TRUE(pp::validateWorkflowDefinition(terminal));
  EXPECT_EQ("WORKFLOW_PLAN_ONLY_STATE_TERMINAL", pp::validateWorkflowDefinition(terminal)->code);

  auto non_action = validPlanOnlyWorkflow();
  non_action.forward_states.insert(pp::State::RECOVER_RETREAT);
  non_action.transitions[pp::State::RECOVER_RETREAT] = {pp::State::DONE, pp::State::ERROR};
  non_action.plan_only_states = {pp::State::RECOVER_RETREAT};
  ASSERT_TRUE(pp::validateWorkflowDefinition(non_action));
  EXPECT_EQ("WORKFLOW_PLAN_ONLY_STATE_NOT_FORWARD_ACTION",
            pp::validateWorkflowDefinition(non_action)->code);

  auto unreachable = validPlanOnlyWorkflow();
  unreachable.action_states.insert(pp::State::DESCEND);
  unreachable.forward_states.insert(pp::State::DESCEND);
  unreachable.transitions[pp::State::DESCEND] = {pp::State::DONE, pp::State::ERROR};
  unreachable.plan_only_states = {pp::State::DESCEND};
  ASSERT_TRUE(pp::validateWorkflowDefinition(unreachable));
  EXPECT_EQ("WORKFLOW_PLAN_ONLY_STATE_UNREACHABLE",
            pp::validateWorkflowDefinition(unreachable)->code);

  auto ambiguous = validPlanOnlyWorkflow();
  ambiguous.action_states.insert(pp::State::RECOVER_RETREAT);
  ambiguous.transitions[pp::State::RECOVER_RETREAT] = {pp::State::MOVE_ABOVE_OBJECT,
                                                       pp::State::ERROR};
  ambiguous.plan_only_states = {pp::State::MOVE_ABOVE_OBJECT};
  ASSERT_TRUE(pp::validateWorkflowDefinition(ambiguous));
  EXPECT_EQ("WORKFLOW_PLAN_ONLY_PREDECESSOR_AMBIGUOUS",
            pp::validateWorkflowDefinition(ambiguous)->code);

  auto cycle = validPlanOnlyWorkflow();
  cycle.transitions[pp::State::MOVE_ABOVE_OBJECT].succeeded = pp::State::PREPARE_OPEN_GRIPPER;
  ASSERT_TRUE(pp::validateWorkflowDefinition(cycle));
  EXPECT_EQ("WORKFLOW_FORWARD_SUCCESS_CYCLE", pp::validateWorkflowDefinition(cycle)->code);
}
