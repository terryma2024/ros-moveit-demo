#include "pick_place_common/workflow_definition.hpp"

#include <set>

#include "pick_place_common/run_request_validation.hpp"

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
      !workflow.terminal_states.count(State::ERROR) || (workflow.initial_state != State::IDLE)) {
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
  {
    std::set<State> visited;
    State state = workflow.initial_state;
    while (!workflow.terminal_states.count(state)) {
      if (!visited.insert(state).second) {
        return configurationFailure("WORKFLOW_FORWARD_SUCCESS_CYCLE",
                                    "forward success path contains a cycle");
      }
      const auto transition = workflow.transitions.find(state);
      if (transition == workflow.transitions.end()) {
        break;
      }
      state = transition->second.succeeded;
    }
  }
  for (const auto state : workflow.plan_only_states) {
    if (workflow.terminal_states.count(state)) {
      return configurationFailure("WORKFLOW_PLAN_ONLY_STATE_TERMINAL",
                                  "plan-only state cannot be terminal");
    }
    if (!workflow.action_states.count(state) || !workflow.forward_states.count(state)) {
      return configurationFailure("WORKFLOW_PLAN_ONLY_STATE_NOT_FORWARD_ACTION",
                                  "plan-only state must be a forward action state");
    }
    if (compareForwardPathPosition(workflow, workflow.initial_state, state) ==
        ForwardPathRelation::UNREACHABLE) {
      return configurationFailure("WORKFLOW_PLAN_ONLY_STATE_UNREACHABLE",
                                  "plan-only state is not on the forward success path");
    }
    std::size_t predecessor_count = 0;
    for (const auto & [source, edges] : workflow.transitions) {
      (void)source;
      predecessor_count += edges.succeeded == state ? 1U : 0U;
    }
    if (predecessor_count != 1) {
      return configurationFailure("WORKFLOW_PLAN_ONLY_PREDECESSOR_AMBIGUOUS",
                                  "plan-only state must have exactly one successful predecessor");
    }
  }
  return std::nullopt;
}

State resolveTransition(const WorkflowDefinition & workflow, State from,
                        ActionStatus outcome) noexcept
{
  if (workflow.terminal_states.count(from)) {
    return from;
  }
  const auto transition = workflow.transitions.find(from);
  if (transition == workflow.transitions.end()) {
    return State::ERROR;
  }
  return outcome == ActionStatus::SUCCEEDED ? transition->second.succeeded
                                            : transition->second.failed;
}

StateMachine::StateMachine(const WorkflowDefinition & workflow, State initial) :
    workflow_(&workflow), current_state_(initial)
{
}
State StateMachine::currentState() const noexcept
{
  return current_state_;
}
bool StateMachine::isTerminal() const noexcept
{
  return workflow_->terminal_states.count(current_state_) != 0;
}
State StateMachine::advance(ActionStatus outcome) noexcept
{
  if (isTerminal()) {
    return current_state_;
  }
  current_state_ = resolveTransition(*workflow_, current_state_, outcome);
  return current_state_;
}
}  // namespace pick_place_common
