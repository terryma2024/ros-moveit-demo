#include "panda_gazebo_demo/pick_place/recovery_policy.hpp"

#include <algorithm>
#include <utility>

namespace panda_gazebo_demo::pick_place
{

namespace
{

RecoveryRoute recoveryError(FailureCategory category, std::string code, std::string message)
{
  return {std::nullopt, Failure{category, std::move(code), std::move(message), {}}};
}

}  // namespace

FixedRecoveryPolicy::FixedRecoveryPolicy(
  std::shared_ptr<const PickPlaceTargetPolicy> target_policy,
  double support_height_tolerance)
: target_policy_(std::move(target_policy)),
  support_height_tolerance_(support_height_tolerance)
{
}

RecoveryRoute FixedRecoveryPolicy::select(
  State failed_state, const Failure & original_failure,
  const WorldSnapshot & stopped_world) const
{
  static_cast<void>(failed_state);
  static_cast<void>(original_failure);
  if (!stopped_world.fresh) {
    return recoveryError(FailureCategory::OBSERVATION, "RECOVERY_OBSERVATION_NOT_FRESH",
      "Recovery classification requires a fresh world observation");
  }
  if (!stopped_world.arm_stationary) {
    return recoveryError(FailureCategory::PRECONDITION, "RECOVERY_ROBOT_NOT_STATIONARY",
      "Recovery classification requires a stationary robot");
  }
  if (!stopped_world.gazebo_coke_attached || !stopped_world.moveit_coke_attached) {
    return recoveryError(FailureCategory::WORLD_INCONSISTENCY,
      "RECOVERY_ATTACHMENT_STATE_UNKNOWN",
      "Recovery classification requires both Gazebo and MoveIt attachment facts");
  }
  if (*stopped_world.gazebo_coke_attached && *stopped_world.moveit_coke_attached) {
    if (!target_policy_) {
      return recoveryError(FailureCategory::CONFIGURATION, "RECOVERY_TARGET_POLICY_MISSING",
        "Recovery classification requires a target policy");
    }
    const ObservationResult observation{stopped_world, std::nullopt};
    const auto pick_target = target_policy_->targetPose(
      State::DESCEND, State::CLOSE_GRIPPER, observation);
    const auto place_target = target_policy_->targetPose(
      State::DESCEND_TO_PLACE, State::OPEN_GRIPPER, observation);
    if (!pick_target.target_pose || !place_target.target_pose) {
      return recoveryError(FailureCategory::CONFIGURATION, "RECOVERY_SUPPORT_TARGET_MISSING",
        "Recovery classification could not resolve pick and place support targets");
    }
    const auto support_height = std::max(
      pick_target.target_pose->z, place_target.target_pose->z);
    if (stopped_world.tcp_pose_world.z > support_height + support_height_tolerance_) {
      return {State::RECOVER_LIFT_TO_SAFE_HEIGHT, std::nullopt};
    }
  }
  return {State::RECOVER_OPEN_GRIPPER, std::nullopt};
}

}  // namespace panda_gazebo_demo::pick_place
