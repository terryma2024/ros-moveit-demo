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
class StateMachine : public pick_place_common::StateMachine
{
public:
  explicit StateMachine(State initial = State::IDLE);
};
}  // namespace so101_gazebo_demo::pick_place
