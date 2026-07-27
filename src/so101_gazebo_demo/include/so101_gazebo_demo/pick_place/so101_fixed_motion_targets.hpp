#pragma once

#include <optional>
#include <string>

#include "so101_gazebo_demo/pick_place/so101_motion_planner.hpp"

namespace so101_gazebo_demo::pick_place
{

struct SO101FixedMotionSpec
{
  State state{State::ERROR};
  std::vector<double> logical_start;
  JointMotionTarget target;
  MotionValidationConfig validation;
  double expected_gripper_q6{0.0};
};

class SO101FixedMotionTargetPolicy final : public IJointMotionTargetPolicy
{
public:
  explicit SO101FixedMotionTargetPolicy(SO101Profile profile = SO101Profile::canonical());

  [[nodiscard]] JointMotionTargetResult
  target(State state, State next_state, const ObservationResult & observation) const override;
  [[nodiscard]] std::optional<SO101FixedMotionSpec> spec(State state) const;
  [[nodiscard]] const std::string & version() const noexcept;

private:
  SO101Profile profile_;
  std::string version_{"so101-fixed-table-d20-v5"};
};

}  // namespace so101_gazebo_demo::pick_place
