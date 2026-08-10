#include "so101_gazebo_demo/pick_place/so101_fixed_motion_targets.hpp"

#include <utility>

namespace so101_gazebo_demo::pick_place
{

SO101ConfiguredMotionTargetPolicy::SO101ConfiguredMotionTargetPolicy(
  MotionPolicyConfig motion, ValidationPolicyConfig validation) :
    motion_(std::move(motion)), validation_(std::move(validation)), version_(motion_.policy_id)
{
}

std::optional<SO101FixedMotionSpec> SO101ConfiguredMotionTargetPolicy::spec(State state) const
{
  const auto motion = motion_.states.find(state);
  const auto validation = validation_.states.find(state);
  if (motion == motion_.states.end() || validation == validation_.states.end()) {
    return std::nullopt;
  }
  JointMotionTarget target{motion_.arm_joints,
                           motion->second.waypoints,
                           motion->second.require_waypoint_ladder,
                           motion->second.gripper_q6,
                           validation->second.motion.temporal_contact_policy,
                           motion->second.velocity_scaling,
                           motion->second.acceleration_scaling};
  auto motion_validation = validation->second.motion;
  motion_validation.expected_joint_names = motion_.arm_joints;
  return SO101FixedMotionSpec{state,
                              motion->second.logical_start,
                              std::move(target),
                              std::move(motion_validation),
                              motion->second.require_axial_path_validation,
                              motion->second.gripper_q6};
}

JointMotionTargetResult SO101ConfiguredMotionTargetPolicy::target(State state, State,
                                                                  const ObservationResult &) const
{
  const auto selected = spec(state);
  if (!selected) {
    return {std::nullopt, Failure{FailureCategory::CONFIGURATION,
                                  "SO101_CONFIGURED_MOTION_TARGET_UNAVAILABLE",
                                  "State has no target in configured policy " + version_,
                                  {}}};
  }
  return {selected->target, std::nullopt};
}

const std::string & SO101ConfiguredMotionTargetPolicy::version() const noexcept
{
  return version_;
}

}  // namespace so101_gazebo_demo::pick_place
