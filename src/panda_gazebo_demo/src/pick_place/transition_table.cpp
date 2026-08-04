#include "panda_gazebo_demo/pick_place/transition_table.hpp"

#include "panda_gazebo_demo/pick_place/panda_workflow.hpp"

namespace panda_gazebo_demo::pick_place
{

State TransitionTable::resolve(State from, ActionStatus outcome) noexcept
{
  return pick_place_common::resolveTransition(pandaWorkflowDefinition(), from, outcome);
}

const std::map<State, StateTransitions> & TransitionTable::entries() noexcept
{
  return pandaWorkflowDefinition().transitions;
}

StateMachine::StateMachine(State initial_state) :
    pick_place_common::StateMachine(pandaWorkflowDefinition(), initial_state)
{
}

}  // namespace panda_gazebo_demo::pick_place
