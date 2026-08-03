#pragma once

#include <optional>
#include <string>

#include "so101_gazebo_demo/pick_place/policy_config.hpp"
#include "so101_gazebo_demo/pick_place/so101_motion_planner.hpp"

namespace so101_gazebo_demo::pick_place
{

struct SO101FixedMotionSpec
{
  State state{State::ERROR};
  std::vector<double> logical_start;
  JointMotionTarget target;
  MotionValidationConfig validation;
  bool require_axial_path_validation{false};
  double expected_gripper_q6{0.0};
};

class SO101ConfiguredMotionTargetPolicy final : public IJointMotionTargetPolicy
{
public:
  SO101ConfiguredMotionTargetPolicy(MotionPolicyConfig motion, ValidationPolicyConfig validation);

  [[nodiscard]] JointMotionTargetResult
  target(State state, State next_state, const ObservationResult & observation) const override;
  [[nodiscard]] std::optional<SO101FixedMotionSpec> spec(State state) const;
  [[nodiscard]] const std::string & version() const noexcept;

private:
  MotionPolicyConfig motion_;
  ValidationPolicyConfig validation_;
  std::string version_;
};

using SO101FixedMotionTargetPolicy = SO101ConfiguredMotionTargetPolicy;

}  // namespace so101_gazebo_demo::pick_place
