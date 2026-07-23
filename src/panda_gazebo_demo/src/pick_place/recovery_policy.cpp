#include "panda_gazebo_demo/pick_place/recovery_policy.hpp"

#include <array>
#include <cmath>
#include <utility>

namespace panda_gazebo_demo::pick_place
{

namespace
{

RecoveryRoute recoveryError(FailureCategory category, std::string code, std::string message)
{
  return {std::nullopt, Failure{category, std::move(code), std::move(message), {}}};
}

bool nearPose(const Pose3d & actual, const Pose3d & expected, double position_tolerance,
              double orientation_tolerance_rad)
{
  return positionDistance(actual, expected) <= position_tolerance &&
         orientationDistance(actual, expected) <= orientation_tolerance_rad;
}

bool finitePose(const Pose3d & pose)
{
  return std::isfinite(pose.x) && std::isfinite(pose.y) && std::isfinite(pose.z) &&
         std::isfinite(pose.qx) && std::isfinite(pose.qy) && std::isfinite(pose.qz) &&
         std::isfinite(pose.qw);
}

}  // namespace

FixedRecoveryPolicy::FixedRecoveryPolicy(std::shared_ptr<const PickPlaceTargetPolicy> target_policy,
                                         double tcp_position_tolerance,
                                         double tcp_orientation_tolerance_rad,
                                         double coke_position_tolerance,
                                         double coke_orientation_tolerance_rad,
                                         GripperLimits gripper_limits) :
    target_policy_(std::move(target_policy)), tcp_position_tolerance_(tcp_position_tolerance),
    tcp_orientation_tolerance_rad_(tcp_orientation_tolerance_rad),
    coke_position_tolerance_(coke_position_tolerance),
    coke_orientation_tolerance_rad_(coke_orientation_tolerance_rad), gripper_limits_(gripper_limits)
{
}

RecoveryRoute FixedRecoveryPolicy::select(State failed_state, const Failure & original_failure,
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
    return recoveryError(
      FailureCategory::WORLD_INCONSISTENCY, "RECOVERY_ATTACHMENT_STATE_UNKNOWN",
      "Recovery classification requires both Gazebo and MoveIt attachment facts");
  }
  if (!stopped_world.gazebo_coke_stationary || !*stopped_world.gazebo_coke_stationary) {
    return recoveryError(FailureCategory::PRECONDITION, "RECOVERY_COKE_NOT_STATIONARY",
                         "Recovery classification requires stationary Gazebo Coke evidence");
  }
  if (!stopped_world.gazebo_coke_pose_world || !finitePose(*stopped_world.gazebo_coke_pose_world) ||
      !finitePose(stopped_world.tcp_pose_world)) {
    return recoveryError(FailureCategory::OBSERVATION, "RECOVERY_COKE_POSE_UNKNOWN",
                         "Recovery classification requires finite TCP and Gazebo Coke poses");
  }
  const auto gripper_evidence = gripperEvidence(stopped_world);
  if (!gripper_evidence.finger1_position || !gripper_evidence.finger2_position ||
      !gripper_evidence.finger1_velocity || !gripper_evidence.finger2_velocity) {
    return recoveryError(
      FailureCategory::GRIPPER, "RECOVERY_GRIPPER_STATE_UNKNOWN",
      "Recovery classification requires finite positions and velocities for both fingers");
  }
  if (!target_policy_) {
    return recoveryError(FailureCategory::CONFIGURATION, "RECOVERY_TARGET_POLICY_MISSING",
                         "Recovery classification requires a target policy");
  }
  const bool gazebo_attached = *stopped_world.gazebo_coke_attached;
  const bool moveit_attached = *stopped_world.moveit_coke_attached;
  const bool gripper_open = validateGripperOpen(stopped_world, gripper_limits_).ok;
  const ObservationResult observation{stopped_world, std::nullopt};
  const auto pick_target =
    target_policy_->targetPose(State::DESCEND, State::CLOSE_GRIPPER, observation);
  const auto place_target =
    target_policy_->targetPose(State::DESCEND_TO_PLACE, State::OPEN_GRIPPER, observation);
  const auto above_pick_target = target_policy_->targetPose(
    State::RECOVER_MOVE_ABOVE_PICK, State::RECOVER_DESCEND_TO_PICK, observation);
  const auto safe_target = target_policy_->targetPose(State::RECOVER_LIFT_TO_SAFE_HEIGHT,
                                                      State::RECOVER_MOVE_ABOVE_PICK, observation);
  const auto pick_coke_target =
    supportedCokePose(*target_policy_, State::DESCEND, State::CLOSE_GRIPPER, observation);
  const auto place_coke_target =
    supportedCokePose(*target_policy_, State::DESCEND_TO_PLACE, State::OPEN_GRIPPER, observation);
  const auto above_pick_coke_target = supportedCokePose(
    *target_policy_, State::RECOVER_MOVE_ABOVE_PICK, State::RECOVER_DESCEND_TO_PICK, observation);
  if (!pick_target.target_pose || !place_target.target_pose || !above_pick_target.target_pose ||
      !safe_target.target_pose || !pick_coke_target.target_pose || !place_coke_target.target_pose ||
      !above_pick_coke_target.target_pose) {
    return recoveryError(
      FailureCategory::CONFIGURATION, "RECOVERY_SUPPORT_TARGET_MISSING",
      "Recovery classification could not resolve all recovery and support targets");
  }
  bool positively_supported = false;
  const std::array<std::pair<Pose3d, Pose3d>, 2> support_targets{
    {{*pick_target.target_pose, *pick_coke_target.target_pose},
     {*place_target.target_pose, *place_coke_target.target_pose}}};
  for (const auto & [tcp_target, coke_target] : support_targets) {
    if (nearPose(stopped_world.tcp_pose_world, tcp_target, tcp_position_tolerance_,
                 tcp_orientation_tolerance_rad_) &&
        nearPose(*stopped_world.gazebo_coke_pose_world, coke_target, coke_position_tolerance_,
                 coke_orientation_tolerance_rad_)) {
      positively_supported = true;
      break;
    }
  }
  if (gazebo_attached || moveit_attached) {
    if (positively_supported) {
      if (gripper_open) {
        return {gazebo_attached ? State::RECOVER_DETACH_GAZEBO : State::RECOVER_DETACH_MOVEIT,
                std::nullopt};
      }
      return {State::RECOVER_OPEN_GRIPPER, std::nullopt};
    }
    if (gazebo_attached && moveit_attached) {
      const bool above_pick = nearPose(stopped_world.tcp_pose_world, *above_pick_target.target_pose,
                                       tcp_position_tolerance_, tcp_orientation_tolerance_rad_);
      const bool coke_above_pick =
        nearPose(*stopped_world.gazebo_coke_pose_world, *above_pick_coke_target.target_pose,
                 coke_position_tolerance_, coke_orientation_tolerance_rad_);
      if (above_pick) {
        if (!coke_above_pick) {
          return recoveryError(FailureCategory::WORLD_INCONSISTENCY,
                               "RECOVERY_CARRIED_POSE_INCONSISTENT",
                               "Coke does not follow the TCP at the above-pick recovery boundary");
        }
        return {State::RECOVER_DESCEND_TO_PICK, std::nullopt};
      }
      const auto coke_at_current_tcp = supportedCokePoseFromTcp(stopped_world.tcp_pose_world);
      if (!nearPose(*stopped_world.gazebo_coke_pose_world, coke_at_current_tcp,
                    coke_position_tolerance_, coke_orientation_tolerance_rad_)) {
        return recoveryError(FailureCategory::WORLD_INCONSISTENCY,
                             "RECOVERY_CARRIED_POSE_INCONSISTENT",
                             "Coke does not follow the current TCP during carrying recovery");
      }
      const bool safe_height_reached =
        std::abs(stopped_world.tcp_pose_world.z - safe_target.target_pose->z) <=
        tcp_position_tolerance_;
      return {safe_height_reached ? State::RECOVER_MOVE_ABOVE_PICK
                                  : State::RECOVER_LIFT_TO_SAFE_HEIGHT,
              std::nullopt};
    }
    return recoveryError(
      FailureCategory::WORLD_INCONSISTENCY, "RECOVERY_PARTIAL_ATTACHMENT_UNSUPPORTED",
      "Partial attachment may be released only with positive pick/place support evidence");
  }
  if (!gripper_open) {
    return {State::RECOVER_OPEN_GRIPPER, std::nullopt};
  }
  const auto moveit_coke = stopped_world.moveit_world_object_poses.find("coke");
  if (moveit_coke == stopped_world.moveit_world_object_poses.end() ||
      !finitePose(moveit_coke->second)) {
    return recoveryError(FailureCategory::MOVEIT_SCENE, "RECOVERY_MOVEIT_COKE_POSE_UNKNOWN",
                         "Detached recovery requires a finite MoveIt Coke world pose");
  }
  if (!nearPose(*stopped_world.gazebo_coke_pose_world, moveit_coke->second,
                coke_position_tolerance_, coke_orientation_tolerance_rad_)) {
    return {State::RECOVER_SYNC_WORLD_OBJECT, std::nullopt};
  }
  return {State::RECOVER_RETREAT, std::nullopt};
}

}  // namespace panda_gazebo_demo::pick_place
