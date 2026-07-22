#pragma once

#include <map>

#include "panda_gazebo_demo/pick_place/domain_types.hpp"

namespace panda_gazebo_demo::pick_place
{

struct StateTransitions
{
  State succeeded;
  State failed;
};

class TransitionTable
{
public:
  [[nodiscard]] State resolve(State from, ActionStatus outcome) const noexcept;
  [[nodiscard]] const std::map<State, StateTransitions> & entries() const noexcept;

private:
  static const std::map<State, StateTransitions> kTransitions;
};

class StateMachine
{
public:
  explicit StateMachine(State initial_state = State::IDLE)
  : current_state_(initial_state) {}

  [[nodiscard]] State currentState() const noexcept;
  [[nodiscard]] bool isTerminal() const noexcept;
  [[nodiscard]] State advance(ActionStatus outcome) noexcept;

private:
  TransitionTable transitions_;
  State current_state_;
};

}  // namespace panda_gazebo_demo::pick_place
