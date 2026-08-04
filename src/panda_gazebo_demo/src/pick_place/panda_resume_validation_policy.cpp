#include "panda_gazebo_demo/pick_place/panda_resume_validation_policy.hpp"

#include <algorithm>
#include <cmath>

#include "pick_place_common/checkpoint_validation.hpp"

namespace panda_gazebo_demo::pick_place
{

pick_place_common::ValidationResult
PandaResumeValidationPolicy::validateBoundary(const pick_place_common::Checkpoint & checkpoint,
                                              const pick_place_common::WorldSnapshot & current,
                                              double tolerance) const
{
  using pick_place_common::Failure;
  using pick_place_common::FailureCategory;
  pick_place_common::ValidationResult result{true, {}, {}};
  const auto add_failure = [&result](std::string code, std::string message) {
    result.failures.push_back(
      Failure{FailureCategory::RESUME_VALIDATION, std::move(code), std::move(message), {}});
  };
  if (checkpoint.phase == pick_place_common::CheckpointPhase::RECOVERY &&
      (!checkpoint.failed_state || !checkpoint.original_failure)) {
    add_failure("RECOVERY_CHECKPOINT_CONTEXT_INCOMPLETE",
                "Recovery checkpoints require a failed state and original failure");
  }
  if (current.joint_positions.empty() || !current.moveit_task_object_attached ||
      !current.gazebo_task_object_attached || !current.gazebo_task_object_pose_world) {
    add_failure("RESUME_SNAPSHOT_INCOMPLETE",
                "Resume requires joint, Gazebo pose/attachment, and MoveIt attachment evidence");
  }
  if (checkpoint.expected.joint_positions.empty() ||
      !checkpoint.expected.moveit_task_object_attached ||
      !checkpoint.expected.gazebo_task_object_attached ||
      !checkpoint.expected.gazebo_task_object_pose_world) {
    add_failure("CHECKPOINT_EXPECTATION_INCOMPLETE",
                "Checkpoint is missing required cross-world transition evidence");
  }
  const auto joints = pick_place_common::compareNamedJointPositions(
    checkpoint.expected.joint_positions, current.joint_positions, tolerance);
  result.metrics["resume_joint_position_error_max"] = joints.maximum_error;
  if (!joints.complete || (checkpoint.phase == pick_place_common::CheckpointPhase::FORWARD &&
                           !joints.within_tolerance)) {
    add_failure("RESUME_JOINT_POSITION_MISMATCH",
                checkpoint.phase == pick_place_common::CheckpointPhase::FORWARD
                  ? "Current named joint positions differ from the checkpoint expectation"
                  : "Recovery resume requires complete finite named-joint evidence");
  }
  result.ok = result.failures.empty();
  return result;
}

std::string PandaResumeValidationPolicy::fingerprintMismatchCode() const
{
  return "RESUME_CONFIGURATION_MISMATCH";
}

}  // namespace panda_gazebo_demo::pick_place
