#include "so101_gazebo_demo/pick_place/so101_recovery_policy.hpp"

#include <algorithm>
#include <cmath>
#include <utility>

#include "so101_gazebo_demo/pick_place/so101_gripper_validation.hpp"
#include "so101_gazebo_demo/pick_place/so101_gripper_state.hpp"
#include "so101_gazebo_demo/pick_place/support_pose.hpp"

namespace so101_gazebo_demo::pick_place
{
namespace
{

RecoveryRoute error(FailureCategory category, std::string code, std::string message)
{
  return {std::nullopt, Failure{category, std::move(code), std::move(message), {}}};
}

RecoveryRoute holdForOperator(const Failure & original_failure, std::string reason)
{
  auto failure = original_failure;
  failure.message = std::move(reason) + "; original failure: " + original_failure.code + ": " +
                    original_failure.message;
  failure.metrics["recovery_disposition_hold_for_operator"] = 1.0;
  return {std::nullopt, std::move(failure)};
}

bool currentEvidence(const std::optional<std::chrono::steady_clock::time_point> & observed_at,
                     const WorldSnapshot & current)
{
  return observed_at && *observed_at <= current.observed_at;
}

bool supportedByFreshPhysicalEvidence(const WorldSnapshot & current, const SO101Profile & profile)
{
  return current.gazebo_task_object_intended_support_contact.value_or(false) &&
         currentEvidence(current.gazebo_support_contact_observed_at, current) &&
         currentEvidence(current.gazebo_pose_observed_at, current) &&
         current.gazebo_task_object_pose_world &&
         (supportedAtPick(*current.gazebo_task_object_pose_world, profile) ||
          supportedAtPlace(*current.gazebo_task_object_pose_world, profile));
}

bool postReleaseState(State state)
{
  return state == State::OPEN_GRIPPER || state == State::WAIT_RELEASE_SETTLE ||
         state == State::VALIDATE_FINAL_PLACEMENT || state == State::SYNC_WORLD_OBJECT;
}

bool nearPose(const Pose3d & actual, const Pose3d & expected, const SO101Profile & profile)
{
  return positionDistance(actual, expected) <= profile.task_object_position_drift_tolerance &&
         orientationDistance(actual, expected) <=
           profile.task_object_orientation_drift_tolerance_rad;
}

bool tableCanonical(const WorldSnapshot & current, const SO101Profile & profile)
{
  const auto table = current.moveit_world_object_poses.find(profile.table_object);
  return table != current.moveit_world_object_poses.end() &&
         positionDistance(table->second, profile.table_pose) <= 1e-5 &&
         orientationDistance(table->second, profile.table_pose) <= 1e-4;
}

bool armAtSafeHome(const WorldSnapshot & current, const SO101Profile & profile)
{
  constexpr double kArmHomeTolerance = 0.002;
  for (std::size_t index = 0; index < profile.arm_joints.size(); ++index) {
    const auto position = current.joint_positions.find(profile.arm_joints[index]);
    const auto velocity = current.joint_velocities.find(profile.arm_joints[index]);
    if (position == current.joint_positions.end() || velocity == current.joint_velocities.end() ||
        !std::isfinite(position->second) || !std::isfinite(velocity->second) ||
        std::abs(position->second - profile.arm_home_positions[index]) > kArmHomeTolerance ||
        std::abs(velocity->second) > profile.q6_velocity_tolerance) {
      return false;
    }
  }
  return true;
}

}  // namespace

SO101RecoveryPolicy::SO101RecoveryPolicy(SO101Profile profile) : profile_(std::move(profile)) {}

bool SO101RecoveryPolicy::canSkipRecoveryAction(State, const Failure & original_failure,
                                                State next_recovery_action,
                                                const WorldSnapshot & current) const
{
  const auto unexecuted = original_failure.metrics.find("plan_only_target_not_executed");
  if (next_recovery_action != State::RECOVER_RETREAT ||
      original_failure.category != FailureCategory::PLAN_VALIDATION ||
      unexecuted == original_failure.metrics.end() || unexecuted->second != 1.0 || !current.fresh ||
      !current.arm_stationary || !armAtSafeHome(current, profile_)) {
    return false;
  }
  if (!current.gazebo_task_object_attached || !current.moveit_task_object_attached ||
      *current.gazebo_task_object_attached || *current.moveit_task_object_attached ||
      !current.gazebo_task_object_pose_world || !current.gazebo_task_object_stationary ||
      !*current.gazebo_task_object_stationary ||
      !validateSO101GripperTarget(current, SO101GripperTarget::FULL_OPEN, profile_).ok) {
    return false;
  }
  const auto task_object = current.moveit_world_object_poses.find(profile_.task_object_id);
  return task_object != current.moveit_world_object_poses.end() &&
         nearPose(*current.gazebo_task_object_pose_world, profile_.task_object_pose, profile_) &&
         nearPose(task_object->second, *current.gazebo_task_object_pose_world, profile_) &&
         tableCanonical(current, profile_) && !current.moveit_task_object_attached_link &&
         current.moveit_task_object_touch_links.empty();
}

RecoveryRoute SO101RecoveryPolicy::select(State failed_state, const Failure & original_failure,
                                          const WorldSnapshot & current) const
{
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

  if (postReleaseState(failed_state)) {
    return holdForOperator(original_failure,
                           "Post-release evidence must be preserved without automatic motion");
  }

  const bool gripper_contact = current.gazebo_task_object_gripper_contact.value_or(false) &&
                               currentEvidence(current.gazebo_gripper_contact_observed_at, current);
  const bool physically_held = !gripper_full_open && gripper_contact;
  if (physically_held &&
      (!supportedByFreshPhysicalEvidence(current, profile_) || moveit_attached)) {
    return holdForOperator(original_failure,
                           moveit_attached
                             ? "MoveIt planning shadow must be detached before physical opening"
                             : "Physically held TaskObject lacks fresh support evidence");
  }

  if ((gazebo_attached || moveit_attached) &&
      !nearPose(*current.gazebo_task_object_pose_world, profile_.task_object_pose, profile_)) {
    return error(
      FailureCategory::WORLD_INCONSISTENCY, "UNSAFE_RECOVERY_OBSERVATION",
      "Attached TaskObject is not on the known support pose; carrying recovery is not yet "
      "configured");
  }
  if (!gripper_full_open) {
    if (!supportedByFreshPhysicalEvidence(current, profile_) || moveit_attached) {
      return holdForOperator(original_failure,
                             "Controlled opening requires fresh physical support evidence and a "
                             "detached MoveIt planning shadow");
    }
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
