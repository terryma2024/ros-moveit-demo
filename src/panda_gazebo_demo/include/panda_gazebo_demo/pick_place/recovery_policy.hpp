#pragma once

#include <memory>
#include <optional>

#include "panda_gazebo_demo/pick_place/pick_place_target_policy.hpp"
#include "panda_gazebo_demo/pick_place/state_validation.hpp"

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
    double tcp_position_tolerance, double tcp_orientation_tolerance_rad = 0.035,
    double coke_position_tolerance = 0.010,
    double coke_orientation_tolerance_rad = 0.0872665,
    GripperLimits gripper_limits = {});

  [[nodiscard]] RecoveryRoute select(
    State failed_state, const Failure & original_failure,
    const WorldSnapshot & stopped_world) const override;

private:
  std::shared_ptr<const PickPlaceTargetPolicy> target_policy_;
  double tcp_position_tolerance_;
  double tcp_orientation_tolerance_rad_;
  double coke_position_tolerance_;
  double coke_orientation_tolerance_rad_;
  GripperLimits gripper_limits_;
};

}  // namespace panda_gazebo_demo::pick_place
