#pragma once
#include "pick_place_common/world_observer.hpp"
namespace pick_place_common
{
struct RecoveryRoute
{
  std::optional<State> next_state;
  std::optional<Failure> failure;
};
class IRecoveryPolicy
{
public:
  virtual ~IRecoveryPolicy() = default;
  virtual RecoveryRoute select(State, const Failure &, const WorldSnapshot &) const = 0;
  virtual bool canSkipRecoveryAction(State, const Failure &, State, const WorldSnapshot &) const
  {
    return false;
  }
};
}  // namespace pick_place_common
