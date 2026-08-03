#include "so101_gazebo_demo/pick_place/transition_table.hpp"

#include "so101_gazebo_demo/pick_place/so101_workflow.hpp"

namespace so101_gazebo_demo::pick_place
{

State TransitionTable::resolve(State from, ActionStatus outcome) noexcept
{
  const auto & transitions = so101WorkflowDefinition().transitions;
  const auto it = transitions.find(from);
  return it == transitions.end()
           ? State::ERROR
           : (outcome == ActionStatus::SUCCEEDED ? it->second.succeeded : it->second.failed);
}

const std::map<State, StateTransitions> & TransitionTable::entries() noexcept
{
  return so101WorkflowDefinition().transitions;
}

State StateMachine::advance(ActionStatus outcome) noexcept
{
  if (!isTerminal()) {
    current_state_ = TransitionTable::resolve(current_state_, outcome);
  }
  return current_state_;
}

}  // namespace so101_gazebo_demo::pick_place
