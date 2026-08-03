#include "panda_gazebo_demo/pick_place/panda_resume_validation_policy.hpp"

#include <algorithm>
#include <cmath>

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
  bool joint_evidence_valid =
    checkpoint.expected.joint_positions.size() == current.joint_positions.size();
  bool within_tolerance = true;
  double maximum_error = 0.0;
  for (const auto & [name, expected] : checkpoint.expected.joint_positions) {
    const auto actual = current.joint_positions.find(name);
    if (actual == current.joint_positions.end() || !std::isfinite(expected) ||
        !std::isfinite(actual->second)) {
      joint_evidence_valid = false;
      continue;
    }
    const auto error = std::abs(expected - actual->second);
    maximum_error = std::max(maximum_error, error);
    within_tolerance = within_tolerance && error <= tolerance;
  }
  result.metrics["resume_joint_position_error_max"] = maximum_error;
  if (!joint_evidence_valid ||
      (checkpoint.phase == pick_place_common::CheckpointPhase::FORWARD && !within_tolerance)) {
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
