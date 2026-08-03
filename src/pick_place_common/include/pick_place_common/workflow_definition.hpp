#pragma once

#include <map>
#include <optional>
#include <set>

#include "pick_place_common/domain_types.hpp"

namespace pick_place_common
{
struct StateTransitions
{
  State succeeded;
  State failed;
};

struct WorkflowDefinition
{
  State initial_state{State::IDLE};
  std::map<State, StateTransitions> transitions;
  std::set<State> action_states;
  std::set<State> forward_states;
  std::set<State> terminal_states;
  std::set<State> force_continue_states;
};

[[nodiscard]] std::optional<Failure>
validateWorkflowDefinition(const WorkflowDefinition & workflow);

class StateMachine
{
public:
  StateMachine(const WorkflowDefinition & workflow, State initial);
  [[nodiscard]] State currentState() const noexcept;
  [[nodiscard]] bool isTerminal() const noexcept;
  [[nodiscard]] State advance(ActionStatus outcome) noexcept;

private:
  const WorkflowDefinition * workflow_;
  State current_state_;
};
}  // namespace pick_place_common
