#include "panda_gazebo_demo/pick_place/transition_table.hpp"

#include "panda_gazebo_demo/pick_place/panda_workflow.hpp"

namespace panda_gazebo_demo::pick_place
{

State TransitionTable::resolve(State from, ActionStatus outcome) noexcept
{
  const auto & transitions = pandaWorkflowDefinition().transitions;
  const auto transition = transitions.find(from);
  if (transition == transitions.end()) {
    return State::ERROR;
  }
  return outcome == ActionStatus::SUCCEEDED ? transition->second.succeeded
                                            : transition->second.failed;
}

const std::map<State, StateTransitions> & TransitionTable::entries() noexcept
{
  return pandaWorkflowDefinition().transitions;
}

State StateMachine::currentState() const noexcept
{
  return current_state_;
}

bool StateMachine::isTerminal() const noexcept
{
  return pick_place::isTerminal(current_state_);
}

State StateMachine::advance(ActionStatus outcome) noexcept
{
  if (!isTerminal()) {
    current_state_ = TransitionTable::resolve(current_state_, outcome);
  }
  return current_state_;
}

}  // namespace panda_gazebo_demo::pick_place
