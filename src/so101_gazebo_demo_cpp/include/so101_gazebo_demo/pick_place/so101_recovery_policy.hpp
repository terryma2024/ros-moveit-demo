#pragma once

#include "so101_gazebo_demo/pick_place/recovery_policy.hpp"
#include "so101_gazebo_demo/pick_place/so101_profile.hpp"

namespace so101_gazebo_demo::pick_place
{

class SO101RecoveryPolicy final : public IRecoveryPolicy
{
public:
  explicit SO101RecoveryPolicy(SO101Profile profile = SO101Profile::canonical());

  [[nodiscard]] RecoveryRoute select(State failed_state, const Failure & original_failure,
                                     const WorldSnapshot & current) const override;
  [[nodiscard]] bool canSkipRecoveryAction(State failed_state, const Failure & original_failure,
                                           State next_recovery_action,
                                           const WorldSnapshot & current) const override;

private:
  SO101Profile profile_;
};

}  // namespace so101_gazebo_demo::pick_place
