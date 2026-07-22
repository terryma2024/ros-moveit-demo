#include "panda_gazebo_demo/pick_place/common_resume_validator.hpp"

#include <algorithm>
#include <cmath>
#include <utility>

namespace panda_gazebo_demo::pick_place
{

namespace
{

void addFailure(ValidationResult & result, std::string code, std::string message)
{
  result.failures.push_back(
    {FailureCategory::RESUME_VALIDATION, std::move(code), std::move(message), {}});
}

}  // namespace

CommonResumeValidator::CommonResumeValidator(
  std::string configuration_hash, std::string simulation_session_id,
  double joint_position_tolerance)
: configuration_hash_(std::move(configuration_hash)),
  simulation_session_id_(std::move(simulation_session_id)),
  joint_position_tolerance_(joint_position_tolerance)
{
}

ValidationResult CommonResumeValidator::validate(
  const Checkpoint & checkpoint, const WorldSnapshot & current) const
{
  ValidationResult result{true, {}, {}};
  if (checkpoint.schema_version != 3) {
    addFailure(result, "CHECKPOINT_INCOMPATIBLE",
      "Only checkpoint schema version 3 can be resumed");
  }
  if (checkpoint.phase == CheckpointPhase::RECOVERY &&
    (!checkpoint.failed_state || !checkpoint.original_failure))
  {
    addFailure(result, "RECOVERY_CHECKPOINT_CONTEXT_INCOMPLETE",
      "Recovery checkpoints require a failed state and original failure");
  }
  if (checkpoint.configuration_hash.empty() ||
    checkpoint.configuration_hash != configuration_hash_)
  {
    addFailure(result, "RESUME_CONFIGURATION_MISMATCH",
      "Checkpoint configuration hash differs from the active configuration");
  }
  if (checkpoint.simulation_session_id.empty() ||
    checkpoint.simulation_session_id != simulation_session_id_ ||
    current.simulation_session_id != simulation_session_id_)
  {
    addFailure(result, "RESUME_SIMULATION_SESSION_MISMATCH",
      "Checkpoint, active configuration, and current Gazebo observation must share a session ID");
  }
  if (!current.fresh || !current.arm_stationary) {
    addFailure(result, "RESUME_ARM_NOT_QUIESCENT",
      "Current robot observation must be fresh and stationary before resume");
  }
  if (current.joint_positions.empty() || !current.moveit_coke_attached ||
    !current.gazebo_coke_attached || !current.gazebo_coke_pose_world)
  {
    addFailure(result, "RESUME_SNAPSHOT_INCOMPLETE",
      "Resume requires joint, Gazebo pose/attachment, and MoveIt attachment evidence");
  }
  if (checkpoint.expected.joint_positions.empty() ||
    !checkpoint.expected.moveit_coke_attached ||
    !checkpoint.expected.gazebo_coke_attached ||
    !checkpoint.expected.gazebo_coke_pose_world)
  {
    addFailure(result, "CHECKPOINT_EXPECTATION_INCOMPLETE",
      "Checkpoint is missing required cross-world transition evidence");
  }
  bool joint_evidence_valid =
    checkpoint.expected.joint_positions.size() == current.joint_positions.size();
  bool joint_positions_within_tolerance = true;
  double maximum_joint_position_error = 0.0;
  for (const auto & [name, expected_position] : checkpoint.expected.joint_positions) {
    const auto current_position = current.joint_positions.find(name);
    if (current_position == current.joint_positions.end() ||
      !std::isfinite(expected_position) || !std::isfinite(current_position->second))
    {
      joint_evidence_valid = false;
      continue;
    }
    const auto error = std::abs(expected_position - current_position->second);
    maximum_joint_position_error = std::max(maximum_joint_position_error, error);
    if (error > joint_position_tolerance_) {
      joint_positions_within_tolerance = false;
    }
  }
  result.metrics["resume_joint_position_error_max"] = maximum_joint_position_error;
  const bool forward_joint_mismatch = checkpoint.phase == CheckpointPhase::FORWARD &&
    !joint_positions_within_tolerance;
  if (!joint_evidence_valid || forward_joint_mismatch) {
    addFailure(result, "RESUME_JOINT_POSITION_MISMATCH",
      checkpoint.phase == CheckpointPhase::FORWARD ?
      "Current named joint positions differ from the checkpoint expectation" :
      "Recovery resume requires complete finite named-joint evidence");
  }
  result.ok = result.failures.empty();
  return result;
}

const std::string & CommonResumeValidator::configurationHash() const noexcept
{
  return configuration_hash_;
}

const std::string & CommonResumeValidator::simulationSessionId() const noexcept
{
  return simulation_session_id_;
}

}  // namespace panda_gazebo_demo::pick_place
