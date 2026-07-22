#include "panda_gazebo_demo/pick_place/pick_place_target_policy.hpp"

#include <utility>

namespace panda_gazebo_demo::pick_place
{

namespace
{

constexpr Pose3d move_above_object_target{0.3, 0.0, 0.987, 1.0, 0.0, 0.0, 0.0};
constexpr Pose3d descend_target{0.3, 0.0, 0.93, 1.0, 0.0, 0.0, 0.0};

TargetPoseResult unsupportedTransition(State current_state, State next_state)
{
  return {std::nullopt, Failure{FailureCategory::CONFIGURATION,
      "TARGET_POLICY_UNSUPPORTED_TRANSITION",
      std::string("PickPlaceTargetPolicy does not support ") + toString(current_state) + " -> " +
      toString(next_state), {}}};
}

}  // namespace

TargetPoseResult FixedPickPlaceTargetPolicy::targetPose(
  State current_state, State next_state, const ObservationResult & observation) const
{
  static_cast<void>(observation);
  if (current_state == State::MOVE_ABOVE_OBJECT && next_state == State::DESCEND) {
    return {move_above_object_target, std::nullopt};
  }
  if (current_state == State::DESCEND && next_state == State::CLOSE_GRIPPER) {
    return {descend_target, std::nullopt};
  }
  return unsupportedTransition(current_state, next_state);
}

std::string FixedPickPlaceTargetPolicy::configurationSignature() const
{
  return "fixed-v1|MOVE_ABOVE_OBJECT->DESCEND=0.3,0,0.987,1,0,0,0|"
         "DESCEND->CLOSE_GRIPPER=0.3,0,0.93,1,0,0,0";
}

}  // namespace panda_gazebo_demo::pick_place
