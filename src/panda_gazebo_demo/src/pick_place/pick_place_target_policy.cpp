#include "panda_gazebo_demo/pick_place/pick_place_target_policy.hpp"

#include <sstream>
#include <utility>

namespace panda_gazebo_demo::pick_place
{

namespace
{

constexpr Pose3d above_pick_target{0.3, 0.0, 0.987, 1.0, 0.0, 0.0, 0.0};
constexpr Pose3d pick_target{0.3, 0.0, 0.93, 1.0, 0.0, 0.0, 0.0};
constexpr Pose3d above_place_target{0.3, 0.2, 0.987, 1.0, 0.0, 0.0, 0.0};
constexpr Pose3d place_target{0.3, 0.2, 0.93, 1.0, 0.0, 0.0, 0.0};

TargetPoseResult unsupportedTransition(State current_state, State next_state)
{
  return {std::nullopt, Failure{FailureCategory::CONFIGURATION,
      "TARGET_POLICY_UNSUPPORTED_TRANSITION",
      std::string("PickPlaceTargetPolicy does not support ") + toString(current_state) + " -> " +
      toString(next_state), {}}};
}

}  // namespace

FixedPickPlaceTargetPolicy::FixedPickPlaceTargetPolicy(double recovery_safe_height)
: recovery_safe_height_(recovery_safe_height)
{
}

TargetPoseResult FixedPickPlaceTargetPolicy::targetPose(
  State current_state, State next_state, const ObservationResult & observation) const
{
  if (current_state == State::MOVE_ABOVE_OBJECT && next_state == State::DESCEND) {
    return {above_pick_target, std::nullopt};
  }
  if (current_state == State::DESCEND && next_state == State::CLOSE_GRIPPER) {
    return {pick_target, std::nullopt};
  }
  if (current_state == State::LIFT && next_state == State::MOVE_ABOVE_PLACE) {
    return {above_pick_target, std::nullopt};
  }
  if (current_state == State::MOVE_ABOVE_PLACE && next_state == State::DESCEND_TO_PLACE) {
    return {above_place_target, std::nullopt};
  }
  if (current_state == State::DESCEND_TO_PLACE && next_state == State::OPEN_GRIPPER) {
    return {place_target, std::nullopt};
  }
  if (current_state == State::RETREAT && next_state == State::DONE) {
    return {above_place_target, std::nullopt};
  }
  if (current_state == State::RECOVER_MOVE_ABOVE_PICK &&
    next_state == State::RECOVER_DESCEND_TO_PICK)
  {
    return {above_pick_target, std::nullopt};
  }
  if (current_state == State::RECOVER_DESCEND_TO_PICK &&
    next_state == State::RECOVER_OPEN_GRIPPER)
  {
    return {pick_target, std::nullopt};
  }
  if ((current_state == State::RECOVER_LIFT_TO_SAFE_HEIGHT &&
    next_state == State::RECOVER_MOVE_ABOVE_PICK) ||
    (current_state == State::RECOVER_RETREAT && next_state == State::ERROR))
  {
    if (!observation.snapshot) {
      return {std::nullopt, Failure{FailureCategory::OBSERVATION,
          "RECOVERY_TARGET_OBSERVATION_MISSING",
          "Recovery safe-height target requires a current world snapshot", {}}};
    }
    auto target = observation.snapshot->tcp_pose_world;
    target.z = recovery_safe_height_;
    return {target, std::nullopt};
  }
  return unsupportedTransition(current_state, next_state);
}

std::string FixedPickPlaceTargetPolicy::configurationSignature() const
{
  std::ostringstream signature;
  signature << "fixed-v2|above_pick=0.3,0,0.987,1,0,0,0|pick=0.3,0,0.93,1,0,0,0|"
            << "above_place=0.3,0.2,0.987,1,0,0,0|place=0.3,0.2,0.93,1,0,0,0|"
            << "recovery_safe_height=" << recovery_safe_height_;
  return signature.str();
}

}  // namespace panda_gazebo_demo::pick_place
