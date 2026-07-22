#include "panda_gazebo_demo/pick_place/transition_table.hpp"

namespace panda_gazebo_demo::pick_place
{

const std::map<State, StateTransitions> TransitionTable::kTransitions{
  {State::IDLE, {State::PREPARE_OPEN_GRIPPER, State::ERROR}},
  {State::PREPARE_OPEN_GRIPPER, {State::MOVE_ABOVE_OBJECT, State::ERROR}},
  {State::MOVE_ABOVE_OBJECT, {State::DESCEND, State::ERROR}},
  {State::DESCEND, {State::CLOSE_GRIPPER, State::RECOVER_OPEN_GRIPPER}},
  {State::CLOSE_GRIPPER, {State::ATTACH_GAZEBO, State::RECOVER_OPEN_GRIPPER}},
  {State::ATTACH_GAZEBO, {State::ATTACH_MOVEIT, State::RECOVER_OPEN_GRIPPER}},
  {State::ATTACH_MOVEIT, {State::LIFT, State::RECOVER_DETACH_MOVEIT}},
  {State::LIFT, {State::MOVE_ABOVE_PLACE, State::ERROR}},
  {State::MOVE_ABOVE_PLACE, {State::DESCEND_TO_PLACE, State::ERROR}},
  {State::DESCEND_TO_PLACE, {State::OPEN_GRIPPER, State::ERROR}},
  {State::OPEN_GRIPPER, {State::DETACH_GAZEBO, State::ERROR}},
  {State::DETACH_GAZEBO, {State::DETACH_MOVEIT, State::ERROR}},
  {State::DETACH_MOVEIT, {State::SYNC_WORLD_OBJECT, State::ERROR}},
  {State::SYNC_WORLD_OBJECT, {State::RETREAT, State::ERROR}},
  {State::RETREAT, {State::DONE, State::ERROR}},
  {State::RECOVER_DETACH_MOVEIT, {State::RECOVER_OPEN_GRIPPER, State::ERROR}},
  {State::RECOVER_OPEN_GRIPPER, {State::RECOVER_DETACH_GAZEBO, State::ERROR}},
  {State::RECOVER_DETACH_GAZEBO, {State::RECOVER_SYNC_WORLD_OBJECT, State::ERROR}},
  {State::RECOVER_SYNC_WORLD_OBJECT, {State::RECOVER_RETREAT, State::ERROR}},
  {State::RECOVER_RETREAT, {State::ERROR, State::ERROR}},
};

State TransitionTable::resolve(State from, ActionStatus outcome) const noexcept
{
  const auto transition = kTransitions.find(from);
  if (transition == kTransitions.end()) {
    return State::ERROR;
  }

  return outcome ==
         ActionStatus::SUCCEEDED ? transition->second.succeeded : transition->second.failed;
}

const std::map<State, StateTransitions> & TransitionTable::entries() const noexcept
{
  return kTransitions;
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
    current_state_ = transitions_.resolve(current_state_, outcome);
  }
  return current_state_;
}

}  // namespace panda_gazebo_demo::pick_place
