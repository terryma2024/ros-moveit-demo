#pragma once
#include <map>
#include "so101_gazebo_demo/pick_place/domain_types.hpp"
#include <pick_place_common/workflow_definition.hpp>
namespace so101_gazebo_demo::pick_place
{
using pick_place_common::StateTransitions;
class TransitionTable
{
public:
  [[nodiscard]] static State resolve(State from, ActionStatus outcome) noexcept;
  [[nodiscard]] static const std::map<State, StateTransitions> & entries() noexcept;
};
class StateMachine
{
public:
  explicit StateMachine(State initial = State::IDLE) : current_state_(initial) {}
  [[nodiscard]] State currentState() const noexcept
  {
    return current_state_;
  }
  [[nodiscard]] bool isTerminal() const noexcept
  {
    return pick_place::isTerminal(current_state_);
  }
  [[nodiscard]] State advance(ActionStatus outcome) noexcept;

private:
  State current_state_;
};
}  // namespace so101_gazebo_demo::pick_place
