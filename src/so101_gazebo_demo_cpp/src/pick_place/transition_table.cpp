#include "so101_gazebo_demo/pick_place/transition_table.hpp"

#include "so101_gazebo_demo/pick_place/so101_workflow.hpp"

namespace so101_gazebo_demo::pick_place
{

State TransitionTable::resolve(State from, ActionStatus outcome) noexcept
{
  return pick_place_common::resolveTransition(so101WorkflowDefinition(), from, outcome);
}

const std::map<State, StateTransitions> & TransitionTable::entries() noexcept
{
  return so101WorkflowDefinition().transitions;
}

StateMachine::StateMachine(State initial) :
    pick_place_common::StateMachine(so101WorkflowDefinition(), initial)
{
}

}  // namespace so101_gazebo_demo::pick_place
