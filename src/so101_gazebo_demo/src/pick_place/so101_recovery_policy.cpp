#include "so101_gazebo_demo/pick_place/so101_recovery_policy.hpp"

#include <algorithm>
#include <cmath>
#include <utility>

#include "so101_gazebo_demo/pick_place/so101_gripper_validation.hpp"
#include "so101_gazebo_demo/pick_place/so101_gripper_state.hpp"

namespace so101_gazebo_demo::pick_place
{
namespace
{

RecoveryRoute error(FailureCategory category, std::string code, std::string message)
{
  return {std::nullopt, Failure{category, std::move(code), std::move(message), {}}};
}

double positionDistance(const Pose3d & first, const Pose3d & second)
{
  return std::hypot(std::hypot(first.x - second.x, first.y - second.y), first.z - second.z);
}

double orientationDistance(const Pose3d & first, const Pose3d & second)
{
  const double first_norm =
    std::hypot(std::hypot(first.qx, first.qy), std::hypot(first.qz, first.qw));
  const double second_norm =
    std::hypot(std::hypot(second.qx, second.qy), std::hypot(second.qz, second.qw));
  if (!std::isfinite(first_norm) || !std::isfinite(second_norm) || first_norm <= 1e-12 ||
      second_norm <= 1e-12) {
    return INFINITY;
  }
  const double dot = std::abs((first.qx * second.qx + first.qy * second.qy +
                               first.qz * second.qz + first.qw * second.qw) /
                              (first_norm * second_norm));
  return 2.0 * std::acos(std::clamp(dot, 0.0, 1.0));
}

bool nearPose(const Pose3d & actual, const Pose3d & expected, const SO101Profile & profile)
{
  return positionDistance(actual, expected) <= profile.task_object_position_drift_tolerance &&
         orientationDistance(actual, expected) <= profile.task_object_orientation_drift_tolerance_rad;
}

bool tableCanonical(const WorldSnapshot & current, const SO101Profile & profile)
{
  const auto table = current.moveit_world_object_poses.find(profile.table_object);
  return table != current.moveit_world_object_poses.end() &&
         positionDistance(table->second, profile.table_pose) <= 1e-5 &&
         orientationDistance(table->second, profile.table_pose) <= 1e-4;
}

}  // namespace

SO101RecoveryPolicy::SO101RecoveryPolicy(SO101Profile profile) : profile_(std::move(profile)) {}

RecoveryRoute SO101RecoveryPolicy::select(State failed_state, const Failure & original_failure,
                                          const WorldSnapshot & current) const
{
  static_cast<void>(failed_state);
  static_cast<void>(original_failure);
  if (!current.fresh) {
    return error(FailureCategory::OBSERVATION, "RECOVERY_OBSERVATION_NOT_FRESH",
                 "Recovery classification requires a fresh observation");
  }
  if (!current.arm_stationary) {
    return error(FailureCategory::PRECONDITION, "RECOVERY_ROBOT_NOT_STATIONARY",
                 "Recovery classification requires a stationary arm");
  }
  if (!current.gazebo_task_object_attached || !current.moveit_task_object_attached) {
    return error(FailureCategory::WORLD_INCONSISTENCY, "RECOVERY_ATTACHMENT_STATE_UNKNOWN",
                 "Recovery requires both current attachment facts");
  }
  if (!current.gazebo_task_object_pose_world || !current.gazebo_task_object_stationary ||
      !*current.gazebo_task_object_stationary) {
    return error(FailureCategory::OBSERVATION, "RECOVERY_TASK_OBJECT_OBSERVATION_INCOMPLETE",
                 "Recovery requires a stationary Gazebo TaskObject pose");
  }
  const auto q6 = current.joint_positions.find(profile_.gripper_joint);
  const auto q6_velocity = current.joint_velocities.find(profile_.gripper_joint);
  if (q6 == current.joint_positions.end() || q6_velocity == current.joint_velocities.end() ||
      !std::isfinite(q6->second) || !std::isfinite(q6_velocity->second)) {
    return error(FailureCategory::GRIPPER, "RECOVERY_GRIPPER_STATE_UNKNOWN",
                 "Recovery requires finite current joint 6 position and velocity");
  }
  if (std::abs(q6_velocity->second) > profile_.q6_velocity_tolerance) {
    return error(FailureCategory::GRIPPER, "RECOVERY_GRIPPER_NOT_STATIONARY",
                 "Recovery requires joint 6 to be stationary");
  }

  const bool gazebo_attached = *current.gazebo_task_object_attached;
  const bool moveit_attached = *current.moveit_task_object_attached;
  const bool gripper_full_open =
    validateSO101GripperTarget(current, SO101GripperTarget::FULL_OPEN, profile_).ok;

  if ((gazebo_attached || moveit_attached) &&
      !nearPose(*current.gazebo_task_object_pose_world, profile_.task_object_pose, profile_)) {
    return error(FailureCategory::WORLD_INCONSISTENCY, "UNSAFE_RECOVERY_OBSERVATION",
                 "Attached TaskObject is not on the known support pose; carrying recovery is not yet "
                 "configured");
  }
  if (!gripper_full_open) {
    return {State::RECOVER_OPEN_GRIPPER, std::nullopt};
  }
  if (gazebo_attached) {
    return {State::RECOVER_DETACH_GAZEBO, std::nullopt};
  }
  if (moveit_attached) {
    return {State::RECOVER_DETACH_MOVEIT, std::nullopt};
  }

  const auto moveit_task_object = current.moveit_world_object_poses.find(profile_.task_object_id);
  const bool task_object_synchronized =
    moveit_task_object != current.moveit_world_object_poses.end() &&
    nearPose(moveit_task_object->second, *current.gazebo_task_object_pose_world, profile_);
  if (!task_object_synchronized || !tableCanonical(current, profile_) ||
      current.moveit_task_object_attached_link || !current.moveit_task_object_touch_links.empty()) {
    return {State::RECOVER_SYNC_WORLD_OBJECT, std::nullopt};
  }
  return {State::RECOVER_RETREAT, std::nullopt};
}

}  // namespace so101_gazebo_demo::pick_place
