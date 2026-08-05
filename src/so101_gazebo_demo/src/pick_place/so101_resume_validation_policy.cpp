#include "so101_gazebo_demo/pick_place/so101_resume_validation_policy.hpp"

#include <algorithm>
#include <cmath>
#include <set>
#include <utility>

#include "so101_gazebo_demo/pick_place/common_resume_validator.hpp"
#include "pick_place_common/checkpoint_validation.hpp"

namespace so101_gazebo_demo::pick_place
{
namespace
{

void addFailure(pick_place_common::ValidationResult & result, std::string code, std::string message)
{
  result.failures.push_back(
    {FailureCategory::RESUME_VALIDATION, std::move(code), std::move(message), {}});
}

bool poseIsFinite(const Pose3d & pose) noexcept
{
  return std::isfinite(pose.x) && std::isfinite(pose.y) && std::isfinite(pose.z) &&
         std::isfinite(pose.qx) && std::isfinite(pose.qy) && std::isfinite(pose.qz) &&
         std::isfinite(pose.qw);
}

double positionError(const Pose3d & expected, const Pose3d & current) noexcept
{
  return std::hypot(std::hypot(expected.x - current.x, expected.y - current.y),
                    expected.z - current.z);
}

double orientationError(const Pose3d & expected, const Pose3d & current) noexcept
{
  // Resume schema v3 owns this sign-invariant quaternion chord metric, not angular distance.
  const auto direct = std::hypot(std::hypot(expected.qx - current.qx, expected.qy - current.qy),
                                 std::hypot(expected.qz - current.qz, expected.qw - current.qw));
  const auto negated = std::hypot(std::hypot(expected.qx + current.qx, expected.qy + current.qy),
                                  std::hypot(expected.qz + current.qz, expected.qw + current.qw));
  return std::min(direct, negated);
}

bool posesMatch(const Pose3d & expected, const Pose3d & current, double tolerance) noexcept
{
  return poseIsFinite(expected) && poseIsFinite(current) &&
         positionError(expected, current) <= tolerance &&
         orientationError(expected, current) <= tolerance;
}

bool poseMapsMatch(const std::map<std::string, Pose3d> & expected,
                   const std::map<std::string, Pose3d> & current, double tolerance)
{
  if (expected.size() != current.size()) {
    return false;
  }
  return std::all_of(expected.begin(), expected.end(), [&](const auto & item) {
    const auto & [name, expected_pose] = item;
    const auto current_pose = current.find(name);
    return !name.empty() && current_pose != current.end() &&
           posesMatch(expected_pose, current_pose->second, tolerance);
  });
}

bool optionalPosesMatch(const std::optional<Pose3d> & expected,
                        const std::optional<Pose3d> & current, double tolerance)
{
  if (expected.has_value() != current.has_value()) {
    return false;
  }
  return !expected || posesMatch(*expected, *current, tolerance);
}

}  // namespace

pick_place_common::ValidationResult
SO101ResumeValidationPolicy::validateBoundary(const pick_place_common::Checkpoint & checkpoint,
                                              const pick_place_common::WorldSnapshot & current,
                                              double tolerance) const
{
  pick_place_common::ValidationResult result{true, {}, {}};
  const bool forward_boundary = checkpoint.phase == CheckpointPhase::FORWARD;
  if (!checkpoint.resumable) {
    addFailure(result, "CHECKPOINT_INCOMPATIBLE", "Resume requires a resumable checkpoint");
  }
  const bool has_failed_state = checkpoint.failed_state.has_value();
  const bool has_original_failure = checkpoint.original_failure.has_value();
  const bool is_physical_validation_checkpoint =
    checkpoint.phase == CheckpointPhase::FORWARD &&
    checkpoint.last_completed_state == State::VERIFY_PHYSICAL_GRASP &&
    checkpoint.failed_state == State::VERIFY_PHYSICAL_GRASP &&
    checkpoint.next_state == State::VALIDATION_FAILED && checkpoint.original_failure &&
    checkpoint.original_failure->category == FailureCategory::POSTCONDITION &&
    checkpoint.original_failure->code.rfind("PHYSICAL_GRASP_", 0) == 0;
  if (checkpoint.source_mode == RunMode::DRY_RUN ||
      (checkpoint.phase == CheckpointPhase::RECOVERY &&
       checkpoint.source_mode != RunMode::EXECUTE)) {
    addFailure(result, "CHECKPOINT_INCOMPATIBLE",
               "Recovery checkpoints must originate from execute mode");
  }
  if (has_failed_state != has_original_failure ||
      (checkpoint.phase == CheckpointPhase::RECOVERY && !has_failed_state) ||
      (checkpoint.phase == CheckpointPhase::FORWARD && has_failed_state &&
       !is_physical_validation_checkpoint)) {
    addFailure(result, "RECOVERY_CHECKPOINT_CONTEXT_INCOMPLETE",
               "Checkpoint recovery context must match its phase");
  }
  if (checkpoint.phase == CheckpointPhase::RECOVERY &&
      (!current.gazebo_task_object_stationary || !*current.gazebo_task_object_stationary)) {
    addFailure(result, "RECOVERY_TASK_OBJECT_NOT_STATIONARY",
               "Recovery resume requires stationary Gazebo object evidence");
  }

  const bool expected_complete = !checkpoint.expected.joint_positions.empty() &&
                                 !checkpoint.expected.moveit_world_object_poses.empty() &&
                                 checkpoint.expected.moveit_task_object_attached.has_value() &&
                                 checkpoint.expected.gazebo_task_object_pose_world.has_value() &&
                                 checkpoint.expected.gazebo_task_object_attached.has_value() &&
                                 checkpoint.expected.gazebo_task_object_stationary.has_value() &&
                                 !checkpoint.expected.required_world_objects.empty();
  if (!expected_complete || !poseIsFinite(checkpoint.expected.tcp_pose_world) ||
      !pick_place_common::hasFiniteJointPositions(checkpoint.expected.joint_positions) ||
      !pick_place_common::hasFinitePoseMap(checkpoint.expected.moveit_world_object_poses)) {
    addFailure(result, "CHECKPOINT_EXPECTATION_INCOMPLETE",
               "Checkpoint is missing complete finite cross-world boundary evidence");
  }
  const bool current_complete = !current.joint_positions.empty() &&
                                !current.moveit_world_object_poses.empty() &&
                                current.moveit_task_object_attached.has_value() &&
                                current.gazebo_task_object_pose_world.has_value() &&
                                current.gazebo_task_object_attached.has_value() &&
                                current.gazebo_task_object_stationary.has_value();
  if (!current_complete || !poseIsFinite(current.tcp_pose_world) ||
      !pick_place_common::hasFiniteJointPositions(current.joint_positions) ||
      !pick_place_common::hasFinitePoseMap(current.moveit_world_object_poses) ||
      !poseIsFinite(*current.gazebo_task_object_pose_world)) {
    addFailure(result, "RESUME_SNAPSHOT_INCOMPLETE",
               "Current observation is missing complete finite cross-world boundary evidence");
  }

  const auto tcp_position_error =
    positionError(checkpoint.expected.tcp_pose_world, current.tcp_pose_world);
  const auto tcp_orientation_error =
    orientationError(checkpoint.expected.tcp_pose_world, current.tcp_pose_world);
  result.metrics["resume_tcp_position_error"] = tcp_position_error;
  result.metrics["resume_tcp_orientation_error"] = tcp_orientation_error;
  if (forward_boundary &&
      !posesMatch(checkpoint.expected.tcp_pose_world, current.tcp_pose_world, tolerance)) {
    addFailure(result, "RESUME_TCP_POSE_MISMATCH",
               "Current TCP pose differs from the checkpoint expectation");
  }
  if (forward_boundary && checkpoint.expected.gripper_open != current.gripper_open) {
    addFailure(result, "RESUME_GRIPPER_STATE_MISMATCH",
               "Current gripper state differs from the checkpoint expectation");
  }

  const auto joints = pick_place_common::compareNamedJointPositions(
    checkpoint.expected.joint_positions, current.joint_positions, tolerance);
  result.metrics["resume_joint_position_error_max"] = joints.maximum_error;
  if (forward_boundary && (!joints.complete || !joints.within_tolerance)) {
    addFailure(result, "RESUME_JOINT_POSITION_MISMATCH",
               "Current named joint positions differ from the checkpoint expectation");
  }

  if (forward_boundary && !poseMapsMatch(checkpoint.expected.moveit_world_object_poses,
                                         current.moveit_world_object_poses, tolerance)) {
    addFailure(result, "RESUME_MOVEIT_WORLD_MISMATCH",
               "Current MoveIt world poses differ from the checkpoint expectation");
  }
  std::set<std::string> required_objects;
  bool required_objects_present = true;
  for (const auto & name : checkpoint.expected.required_world_objects) {
    required_objects_present = required_objects_present && !name.empty() &&
                               required_objects.insert(name).second &&
                               checkpoint.expected.moveit_world_object_poses.count(name) != 0 &&
                               current.moveit_world_object_poses.count(name) != 0;
  }
  if (forward_boundary && !required_objects_present) {
    addFailure(result, "RESUME_REQUIRED_WORLD_OBJECT_MISSING",
               "A required world object is absent or duplicated at the resume boundary");
  }
  if (forward_boundary &&
      checkpoint.expected.moveit_task_object_attached != current.moveit_task_object_attached) {
    addFailure(result, "RESUME_MOVEIT_ATTACHMENT_MISMATCH",
               "Current MoveIt attachment state differs from the checkpoint expectation");
  }
  if (forward_boundary && !optionalPosesMatch(checkpoint.expected.gazebo_task_object_pose_world,
                                              current.gazebo_task_object_pose_world, tolerance)) {
    addFailure(result, "RESUME_GAZEBO_POSE_MISMATCH",
               "Current Gazebo object pose differs from the checkpoint expectation");
  }
  if (forward_boundary &&
      checkpoint.expected.gazebo_task_object_attached != current.gazebo_task_object_attached) {
    addFailure(result, "RESUME_GAZEBO_ATTACHMENT_MISMATCH",
               "Current Gazebo attachment state differs from the checkpoint expectation");
  }
  if (forward_boundary &&
      checkpoint.expected.gazebo_task_object_stationary != current.gazebo_task_object_stationary) {
    addFailure(result, "RESUME_GAZEBO_STATIONARY_MISMATCH",
               "Current Gazebo stationary state differs from the checkpoint expectation");
  }
  result.ok = result.failures.empty();
  return result;
}

std::string SO101ResumeValidationPolicy::fingerprintMismatchCode() const
{
  return "CHECKPOINT_POLICY_MISMATCH";
}

}  // namespace so101_gazebo_demo::pick_place
