#include <gtest/gtest.h>

#include "pick_place_common/workflow_definition.hpp"

namespace pp = pick_place_common;

TEST(WorkflowDefinition, RejectsMissingTransitionAndUnknownTarget)
{
  pp::WorkflowDefinition missing;
  missing.initial_state = pp::State::IDLE;
  missing.action_states = {pp::State::PREPARE_OPEN_GRIPPER};
  missing.terminal_states = {pp::State::DONE, pp::State::ERROR};
  auto failure = pp::validateWorkflowDefinition(missing);
  ASSERT_TRUE(failure);
  EXPECT_EQ("WORKFLOW_TRANSITION_MISSING", failure->code);

  missing.transitions[pp::State::IDLE] =
    {pp::State::PREPARE_OPEN_GRIPPER, pp::State::ERROR};
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
  workflow.transitions[pp::State::IDLE] =
    {pp::State::PREPARE_OPEN_GRIPPER, pp::State::ERROR};
  workflow.transitions[pp::State::PREPARE_OPEN_GRIPPER] =
    {pp::State::DONE, pp::State::ERROR};
  workflow.action_states = {pp::State::PREPARE_OPEN_GRIPPER};
  workflow.forward_states = {pp::State::IDLE, pp::State::PREPARE_OPEN_GRIPPER, pp::State::DONE};
  workflow.terminal_states = {pp::State::DONE, pp::State::ERROR};
  EXPECT_FALSE(pp::validateWorkflowDefinition(workflow));
  pp::StateMachine machine(workflow, pp::State::IDLE);
  EXPECT_EQ(pp::State::PREPARE_OPEN_GRIPPER, machine.advance(pp::ActionStatus::SUCCEEDED));
  EXPECT_EQ(pp::State::DONE, machine.advance(pp::ActionStatus::SUCCEEDED));
}
