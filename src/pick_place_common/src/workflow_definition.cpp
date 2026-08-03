#include "pick_place_common/workflow_definition.hpp"

namespace pick_place_common
{
namespace
{
Failure configurationFailure(const char * code, const char * message)
{
  return {FailureCategory::CONFIGURATION, code, message, {}};
}
}  // namespace

std::optional<Failure> validateWorkflowDefinition(const WorkflowDefinition & workflow)
{
  if (!workflow.terminal_states.count(State::DONE) ||
      !workflow.terminal_states.count(State::ERROR) ||
      (workflow.initial_state != State::IDLE)) {
    return configurationFailure("WORKFLOW_BOUNDARY_MISSING",
                                "workflow must contain IDLE, DONE, and ERROR boundaries");
  }
  for (const auto state : workflow.action_states) {
    if (workflow.terminal_states.count(state)) {
      return configurationFailure("WORKFLOW_TERMINAL_ACTION_OVERLAP",
                                  "terminal state cannot also be an action state");
    }
  }
  for (const auto state : workflow.force_continue_states) {
    if (!workflow.action_states.count(state) && !workflow.transitions.count(state)) {
      return configurationFailure("WORKFLOW_FORCE_CONTINUE_STATE_UNKNOWN",
                                  "force-continue state is not in this workflow");
    }
  }
  std::set<State> declared = workflow.action_states;
  declared.insert(workflow.forward_states.begin(), workflow.forward_states.end());
  declared.insert(workflow.terminal_states.begin(), workflow.terminal_states.end());
  declared.insert(workflow.initial_state);
  for (const auto & [state, edges] : workflow.transitions) {
    declared.insert(state);
    if (!declared.count(edges.succeeded) || !declared.count(edges.failed)) {
      return configurationFailure("WORKFLOW_TRANSITION_TARGET_UNKNOWN",
                                  "transition points to an undeclared state");
    }
    for (const auto target : {edges.succeeded, edges.failed}) {
      if (!workflow.terminal_states.count(target) && !workflow.transitions.count(target)) {
        return configurationFailure("WORKFLOW_TRANSITION_TARGET_UNKNOWN",
                                    "transition target has no workflow definition");
      }
    }
  }
  for (const auto state : workflow.action_states) {
    if (!workflow.transitions.count(state)) {
      return configurationFailure("WORKFLOW_TRANSITION_MISSING",
                                  "non-terminal action state has no transition");
    }
  }
  for (const auto state : declared) {
    if (!workflow.terminal_states.count(state) && !workflow.transitions.count(state)) {
      return configurationFailure("WORKFLOW_TRANSITION_MISSING",
                                  "non-terminal state has no transition");
    }
  }
  return std::nullopt;
}

StateMachine::StateMachine(const WorkflowDefinition & workflow, State initial)
: workflow_(&workflow), current_state_(initial)
{
}
State StateMachine::currentState() const noexcept { return current_state_; }
bool StateMachine::isTerminal() const noexcept
{
  return workflow_->terminal_states.count(current_state_) != 0;
}
State StateMachine::advance(ActionStatus outcome) noexcept
{
  if (isTerminal()) {
    return current_state_;
  }
  const auto transition = workflow_->transitions.find(current_state_);
  if (transition == workflow_->transitions.end()) {
    current_state_ = State::ERROR;
  } else {
    current_state_ = outcome == ActionStatus::SUCCEEDED ? transition->second.succeeded
                                                        : transition->second.failed;
  }
  return current_state_;
}
}  // namespace pick_place_common
