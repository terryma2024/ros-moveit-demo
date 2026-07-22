#pragma once

#include <memory>
#include <optional>

#include "panda_gazebo_demo/pick_place/pick_place_target_policy.hpp"

namespace panda_gazebo_demo::pick_place
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
  [[nodiscard]] virtual RecoveryRoute select(
    State failed_state, const Failure & original_failure,
    const WorldSnapshot & stopped_world) const = 0;
};

class FixedRecoveryPolicy final : public IRecoveryPolicy
{
public:
  FixedRecoveryPolicy(
    std::shared_ptr<const PickPlaceTargetPolicy> target_policy,
    double support_height_tolerance);

  [[nodiscard]] RecoveryRoute select(
    State failed_state, const Failure & original_failure,
    const WorldSnapshot & stopped_world) const override;

private:
  std::shared_ptr<const PickPlaceTargetPolicy> target_policy_;
  double support_height_tolerance_;
};

}  // namespace panda_gazebo_demo::pick_place
