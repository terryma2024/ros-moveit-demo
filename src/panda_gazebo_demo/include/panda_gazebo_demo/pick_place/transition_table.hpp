#pragma once

#include <map>

#include "panda_gazebo_demo/pick_place/domain_types.hpp"
#include <pick_place_common/workflow_definition.hpp>

namespace panda_gazebo_demo::pick_place
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
  explicit StateMachine(State initial_state = State::IDLE) : current_state_(initial_state) {}

  [[nodiscard]] State currentState() const noexcept;
  [[nodiscard]] bool isTerminal() const noexcept;
  [[nodiscard]] State advance(ActionStatus outcome) noexcept;

private:
  State current_state_;
};

}  // namespace panda_gazebo_demo::pick_place
