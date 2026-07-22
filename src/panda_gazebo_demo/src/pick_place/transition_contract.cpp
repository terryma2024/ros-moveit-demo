#include "panda_gazebo_demo/pick_place/transition_contract.hpp"

#include <utility>

#include "panda_gazebo_demo/pick_place/transition_table.hpp"

namespace panda_gazebo_demo::pick_place
{

namespace
{

void addFailure(
  ValidationResult & result, FailureCategory category, std::string code,
  std::string message)
{
  result.failures.push_back({category, std::move(code), std::move(message), {}});
}

void validateCrossWorldConsistency(
  ValidationResult & result, const WorldSnapshot & snapshot, double coke_position_tolerance,
  double coke_orientation_tolerance_rad)
{
  if (!snapshot.gazebo_coke_attached || !snapshot.moveit_coke_attached ||
    !snapshot.gazebo_coke_pose_world)
  {
    addFailure(result, FailureCategory::WORLD_INCONSISTENCY, "CROSS_WORLD_EVIDENCE_UNAVAILABLE",
      "Gazebo Coke pose/attachment and MoveIt attachment state are required");
    return;
  }
  if (*snapshot.gazebo_coke_attached != *snapshot.moveit_coke_attached) {
    addFailure(result, FailureCategory::WORLD_INCONSISTENCY, "COKE_ATTACHMENT_MISMATCH",
      "Gazebo and MoveIt disagree about whether Coke is attached");
    return;
  }
  if (*snapshot.gazebo_coke_attached) {
    return;
  }
  const auto moveit_coke = snapshot.moveit_world_object_poses.find("coke");
  if (moveit_coke == snapshot.moveit_world_object_poses.end()) {
    addFailure(result, FailureCategory::WORLD_INCONSISTENCY, "MOVEIT_COKE_POSE_UNAVAILABLE",
      "Detached Coke must have a MoveIt Planning Scene pose");
    return;
  }
  const auto position_error = positionDistance(*snapshot.gazebo_coke_pose_world,
        moveit_coke->second);
  const auto orientation_error = orientationDistance(
    *snapshot.gazebo_coke_pose_world, moveit_coke->second);
  result.metrics["gazebo_moveit_coke_position_error"] = position_error;
  result.metrics["gazebo_moveit_coke_orientation_error_rad"] = orientation_error;
  if (position_error > coke_position_tolerance ||
    orientation_error > coke_orientation_tolerance_rad)
  {
    addFailure(result, FailureCategory::WORLD_INCONSISTENCY, "COKE_POSE_MISMATCH",
      "Gazebo and MoveIt Coke poses differ beyond the configured tolerance");
  }
}

}  // namespace

void TransitionContractRegistry::registerContract(
  TransitionKey key, std::shared_ptr<const ITransitionContract> contract)
{
  contracts_[key] = std::move(contract);
}
bool TransitionContractRegistry::hasContract(TransitionKey key) const noexcept
{
  return contracts_.count(key) != 0;
}

ValidationResult TransitionContractRegistry::validate(
  TransitionKey key,
  const WorldSnapshot & before,
  const WorldSnapshot & after,
  const ActionResult & action_result) const
{
  const auto found = contracts_.find(key);
  if (found == contracts_.end() || !found->second) {
    return {false,
      {{FailureCategory::CONFIGURATION,
        "MISSING_TRANSITION_CONTRACT",
        std::string("No execute transition contract registered for ") + toString(key.from) +
        " -> " + toString(key.to),
        {}}},
      {}};
  }
  return found->second->validate(before, after, action_result);
}

ValidationResult
TransitionContractRegistry::validatePrecondition(
  TransitionKey key,
  const WorldSnapshot & before) const
{
  const auto found = contracts_.find(key);
  if (found == contracts_.end() || !found->second) {
    return {false,
      {{FailureCategory::CONFIGURATION,
        "MISSING_TRANSITION_CONTRACT",
        std::string("No execute transition contract registered for ") + toString(key.from) +
        " -> " + toString(key.to),
        {}}},
      {}};
  }
  return found->second->validatePrecondition(before);
}

ValidationResult TransitionContractRegistry::validateResume(
  TransitionKey key, const WorldSnapshot & expected, const WorldSnapshot & current) const
{
  return validate(key, expected, current, {ActionStatus::SUCCEEDED, std::nullopt});
}

std::optional<Failure>
TransitionContractRegistry::validateExecuteCoverage(const TransitionTable & table) const
{
  for (const auto & [from, transitions] : table.entries()) {
    if (isTerminal(from)) {
      continue;
    }
    if (!hasContract({from, transitions.succeeded})) {
      return Failure{
        FailureCategory::CONFIGURATION,
        "MISSING_TRANSITION_CONTRACT",
        std::string("No execute transition contract registered for ") + toString(from) + " -> " +
        toString(transitions.succeeded),
        {},
      };
    }
  }
  return std::nullopt;
}

namespace
{

ValidationResult validateMotionCompletion(
  const WorldSnapshot & before,
  const WorldSnapshot & after,
  const ActionResult & action_result, const Pose3d & target_pose,
  const std::vector<std::string> & required_world_objects, double tcp_position_tolerance,
  double tcp_orientation_tolerance_rad, double coke_position_tolerance,
  double coke_orientation_tolerance_rad, bool require_gripper_open)
{
  ValidationResult result{true, {}, {}};
  if (action_result.status != ActionStatus::SUCCEEDED) {
    addFailure(result, FailureCategory::EXECUTION, "MOTION_EXECUTION_FAILED",
               "MoveIt trajectory execution did not report success");
  }
  if (!before.fresh || !after.fresh) {
    addFailure(result, FailureCategory::OBSERVATION, "STALE_WORLD_SNAPSHOT",
               "Pre- and post-execution world snapshots must be fresh");
  }
  if (!after.arm_stationary) {
    addFailure(result, FailureCategory::POSTCONDITION, "ARM_NOT_QUIESCENT",
               "Arm joint velocities remain above the configured stopped threshold");
  }
  validateCrossWorldConsistency(
    result, before, coke_position_tolerance, coke_orientation_tolerance_rad);
  validateCrossWorldConsistency(
    result, after, coke_position_tolerance, coke_orientation_tolerance_rad);
  if (!after.gazebo_coke_attached || !after.moveit_coke_attached ||
    *after.gazebo_coke_attached || *after.moveit_coke_attached)
  {
    addFailure(result, FailureCategory::WORLD_INCONSISTENCY, "COKE_UNEXPECTEDLY_ATTACHED",
               "Coke must remain detached after MOVE_ABOVE_OBJECT");
  }
  const auto tcp_error = positionDistance(after.tcp_pose_world, target_pose);
  const auto tcp_orientation_error = orientationDistance(after.tcp_pose_world, target_pose);
  result.metrics["tcp_position_error"] = tcp_error;
  result.metrics["tcp_orientation_error_rad"] = tcp_orientation_error;
  if (tcp_error > tcp_position_tolerance) {
    addFailure(result, FailureCategory::POSTCONDITION, "TCP_OUTSIDE_TARGET_TOLERANCE",
               "TCP did not reach the configured target position tolerance");
  }
  if (tcp_orientation_error > tcp_orientation_tolerance_rad) {
    addFailure(result, FailureCategory::POSTCONDITION, "TCP_ORIENTATION_OUTSIDE_TARGET_TOLERANCE",
               "TCP did not reach the configured target orientation tolerance");
  }
  if (require_gripper_open && !after.gripper_open) {
    addFailure(result, FailureCategory::POSTCONDITION, "GRIPPER_NOT_SAFELY_OPEN",
      "Gripper must be open before entering the next motion state");
  }
  for (const auto & object_id : required_world_objects) {
    if (after.moveit_world_object_poses.count(object_id) == 0) {
      addFailure(result, FailureCategory::MOVEIT_SCENE, "REQUIRED_WORLD_OBJECT_MISSING",
                 "Required Planning Scene world object is missing: " + object_id);
    }
  }
  if (!before.gazebo_coke_pose_world || !after.gazebo_coke_pose_world) {
    addFailure(result, FailureCategory::OBSERVATION, "GAZEBO_COKE_POSE_UNAVAILABLE",
      "Gazebo Coke pose is required for post-execution stability validation");
  } else {
    const auto coke_error = positionDistance(
      *before.gazebo_coke_pose_world, *after.gazebo_coke_pose_world);
    result.metrics["coke_position_drift"] = coke_error;
    if (coke_error > coke_position_tolerance) {
      addFailure(result, FailureCategory::POSTCONDITION, "COKE_MOVED_DURING_MOVE_ABOVE",
                 "Coke moved farther than the configured stability tolerance");
    }
  }
  result.ok = result.failures.empty();
  return result;
}

ValidationResult validateMotionPrecondition(
  const WorldSnapshot & before, const std::vector<std::string> & required_world_objects,
  double coke_position_tolerance, double coke_orientation_tolerance_rad,
  bool require_gripper_open)
{
  ValidationResult result{true, {}, {}};
  if (!before.fresh) {
    addFailure(result, FailureCategory::OBSERVATION, "STALE_WORLD_SNAPSHOT",
               "The pre-execution world snapshot must be fresh");
  }
  if (!before.arm_stationary) {
    addFailure(result, FailureCategory::PRECONDITION, "ARM_NOT_QUIESCENT",
               "Arm must be stationary before MOVE_ABOVE_OBJECT");
  }
  if (require_gripper_open && !before.gripper_open) {
    addFailure(result, FailureCategory::PRECONDITION, "GRIPPER_NOT_SAFELY_OPEN",
               "Gripper must be open before the configured motion state");
  }
  validateCrossWorldConsistency(
    result, before, coke_position_tolerance, coke_orientation_tolerance_rad);
  if (!before.gazebo_coke_attached || !before.moveit_coke_attached ||
    *before.gazebo_coke_attached || *before.moveit_coke_attached)
  {
    addFailure(result, FailureCategory::WORLD_INCONSISTENCY, "COKE_UNEXPECTEDLY_ATTACHED",
               "Coke must be detached before MOVE_ABOVE_OBJECT");
  }
  for (const auto & object_id : required_world_objects) {
    if (before.moveit_world_object_poses.count(object_id) == 0) {
      addFailure(result, FailureCategory::MOVEIT_SCENE, "REQUIRED_WORLD_OBJECT_MISSING",
                 "Required Planning Scene world object is missing: " + object_id);
    }
  }
  if (!before.gazebo_coke_pose_world) {
    addFailure(result, FailureCategory::MOVEIT_SCENE, "COKE_POSE_UNAVAILABLE",
               "Coke world pose is required before MOVE_ABOVE_OBJECT");
  }
  result.ok = result.failures.empty();
  return result;
}

}  // namespace

ValidationResult AlwaysPassValidator::validatePrecondition(const WorldSnapshot &) const
{
  return {true, {}, {}};
}

ValidationResult AlwaysPassValidator::validate(
  const WorldSnapshot &, const WorldSnapshot &, const ActionResult &) const
{
  return {true, {}, {}};
}

PrepareOpenGripperToMoveAboveObjectValidator::PrepareOpenGripperToMoveAboveObjectValidator(
  std::vector<std::string> required_world_objects, double tcp_position_tolerance,
  double tcp_orientation_tolerance_rad, double coke_position_tolerance,
  double coke_orientation_tolerance_rad)
: required_world_objects_(std::move(required_world_objects)),
  tcp_position_tolerance_(tcp_position_tolerance),
  tcp_orientation_tolerance_rad_(tcp_orientation_tolerance_rad),
  coke_position_tolerance_(coke_position_tolerance),
  coke_orientation_tolerance_rad_(coke_orientation_tolerance_rad)
{
}

ValidationResult PrepareOpenGripperToMoveAboveObjectValidator::validate(
  const WorldSnapshot & before, const WorldSnapshot & after,
  const ActionResult & action_result) const
{
  ValidationResult result{true, {}, {}};
  if (action_result.status != ActionStatus::SUCCEEDED) {
    addFailure(result, FailureCategory::GRIPPER, "GRIPPER_OPEN_EXECUTION_FAILED",
      "The gripper controller did not report a successful open command");
  }
  if (!before.fresh || !after.fresh) {
    addFailure(result, FailureCategory::OBSERVATION, "STALE_WORLD_SNAPSHOT",
      "Pre- and post-gripper world snapshots must be fresh");
  }
  if (!after.arm_stationary) {
    addFailure(result, FailureCategory::POSTCONDITION, "ARM_NOT_QUIESCENT",
      "Arm joint velocities remain above the configured stopped threshold");
  }
  validateCrossWorldConsistency(
    result, before, coke_position_tolerance_, coke_orientation_tolerance_rad_);
  validateCrossWorldConsistency(
    result, after, coke_position_tolerance_, coke_orientation_tolerance_rad_);
  if (!after.gazebo_coke_attached || !after.moveit_coke_attached ||
    *after.gazebo_coke_attached || *after.moveit_coke_attached)
  {
    addFailure(result, FailureCategory::WORLD_INCONSISTENCY, "COKE_UNEXPECTEDLY_ATTACHED",
      "Coke must remain detached while opening the gripper");
  }
  if (!after.gripper_open) {
    addFailure(result, FailureCategory::GRIPPER, "GRIPPER_NOT_SAFELY_OPEN",
      "Both fingers from /joint_states must reach the safe open range");
  }
  for (const auto & object_id : required_world_objects_) {
    if (after.moveit_world_object_poses.count(object_id) == 0) {
      addFailure(result, FailureCategory::MOVEIT_SCENE, "REQUIRED_WORLD_OBJECT_MISSING",
        "Required Planning Scene world object is missing: " + object_id);
    }
  }
  const auto tcp_position_drift = positionDistance(before.tcp_pose_world, after.tcp_pose_world);
  const auto tcp_orientation_drift = orientationDistance(
    before.tcp_pose_world, after.tcp_pose_world);
  result.metrics["tcp_position_drift"] = tcp_position_drift;
  result.metrics["tcp_orientation_drift_rad"] = tcp_orientation_drift;
  if (tcp_position_drift > tcp_position_tolerance_) {
    addFailure(result, FailureCategory::POSTCONDITION, "TCP_MOVED_DURING_GRIPPER_OPEN",
      "TCP position changed while opening the gripper");
  }
  if (tcp_orientation_drift > tcp_orientation_tolerance_rad_) {
    addFailure(result, FailureCategory::POSTCONDITION, "TCP_ROTATED_DURING_GRIPPER_OPEN",
      "TCP orientation changed while opening the gripper");
  }
  if (!before.gazebo_coke_pose_world || !after.gazebo_coke_pose_world) {
    addFailure(result, FailureCategory::OBSERVATION, "GAZEBO_COKE_POSE_UNAVAILABLE",
      "Gazebo Coke pose is required to validate gripper opening");
  } else {
    const auto coke_position_drift = positionDistance(
      *before.gazebo_coke_pose_world, *after.gazebo_coke_pose_world);
    const auto coke_orientation_drift = orientationDistance(
      *before.gazebo_coke_pose_world, *after.gazebo_coke_pose_world);
    result.metrics["coke_position_drift"] = coke_position_drift;
    result.metrics["coke_orientation_drift_rad"] = coke_orientation_drift;
    if (coke_position_drift > coke_position_tolerance_) {
      addFailure(result, FailureCategory::POSTCONDITION, "COKE_MOVED_DURING_GRIPPER_OPEN",
        "Coke position changed while opening the gripper");
    }
    if (coke_orientation_drift > coke_orientation_tolerance_rad_) {
      addFailure(result, FailureCategory::POSTCONDITION, "COKE_ROTATED_DURING_GRIPPER_OPEN",
        "Coke orientation changed while opening the gripper");
    }
  }
  result.ok = result.failures.empty();
  return result;
}

ValidationResult PrepareOpenGripperToMoveAboveObjectValidator::validatePrecondition(
  const WorldSnapshot & before) const
{
  ValidationResult result{true, {}, {}};
  if (!before.fresh) {
    addFailure(result, FailureCategory::OBSERVATION, "STALE_WORLD_SNAPSHOT",
      "The pre-gripper world snapshot must be fresh");
  }
  if (!before.arm_stationary) {
    addFailure(result, FailureCategory::PRECONDITION, "ARM_NOT_QUIESCENT",
      "Arm must be stationary before opening the gripper");
  }
  validateCrossWorldConsistency(
    result, before, coke_position_tolerance_, coke_orientation_tolerance_rad_);
  if (!before.gazebo_coke_attached || !before.moveit_coke_attached ||
    *before.gazebo_coke_attached || *before.moveit_coke_attached)
  {
    addFailure(result, FailureCategory::WORLD_INCONSISTENCY, "COKE_UNEXPECTEDLY_ATTACHED",
      "Coke must be detached before opening the gripper");
  }
  for (const auto & object_id : required_world_objects_) {
    if (before.moveit_world_object_poses.count(object_id) == 0) {
      addFailure(result, FailureCategory::MOVEIT_SCENE, "REQUIRED_WORLD_OBJECT_MISSING",
        "Required Planning Scene world object is missing: " + object_id);
    }
  }
  result.ok = result.failures.empty();
  return result;
}

MoveAboveObjectToDescendValidator::MoveAboveObjectToDescendValidator(
  Pose3d target_pose, std::vector<std::string> required_world_objects,
  double tcp_position_tolerance, double tcp_orientation_tolerance_rad,
  double coke_position_tolerance, double coke_orientation_tolerance_rad)
: target_pose_(target_pose), required_world_objects_(std::move(required_world_objects)),
  tcp_position_tolerance_(tcp_position_tolerance),
  tcp_orientation_tolerance_rad_(tcp_orientation_tolerance_rad),
  coke_position_tolerance_(coke_position_tolerance),
  coke_orientation_tolerance_rad_(coke_orientation_tolerance_rad)
{
}

ValidationResult MoveAboveObjectToDescendValidator::validate(
  const WorldSnapshot & before, const WorldSnapshot & after,
  const ActionResult & action_result) const
{
  return validateMotionCompletion(
    before, after, action_result, target_pose_, required_world_objects_, tcp_position_tolerance_,
    tcp_orientation_tolerance_rad_, coke_position_tolerance_, coke_orientation_tolerance_rad_,
      true);
}

ValidationResult MoveAboveObjectToDescendValidator::validatePrecondition(
  const WorldSnapshot & before) const
{
  return validateMotionPrecondition(
    before, required_world_objects_, coke_position_tolerance_, coke_orientation_tolerance_rad_,
      false);
}

DescendToCloseGripperValidator::DescendToCloseGripperValidator(
  Pose3d target_pose, std::vector<std::string> required_world_objects,
  double tcp_position_tolerance, double tcp_orientation_tolerance_rad,
  double coke_position_tolerance, double coke_orientation_tolerance_rad)
: target_pose_(target_pose), required_world_objects_(std::move(required_world_objects)),
  tcp_position_tolerance_(tcp_position_tolerance),
  tcp_orientation_tolerance_rad_(tcp_orientation_tolerance_rad),
  coke_position_tolerance_(coke_position_tolerance),
  coke_orientation_tolerance_rad_(coke_orientation_tolerance_rad)
{
}

ValidationResult DescendToCloseGripperValidator::validate(
  const WorldSnapshot & before, const WorldSnapshot & after,
  const ActionResult & action_result) const
{
  return validateMotionCompletion(
    before, after, action_result, target_pose_, required_world_objects_, tcp_position_tolerance_,
    tcp_orientation_tolerance_rad_, coke_position_tolerance_, coke_orientation_tolerance_rad_,
      true);
}

ValidationResult DescendToCloseGripperValidator::validatePrecondition(
  const WorldSnapshot & before) const
{
  return validateMotionPrecondition(
    before, required_world_objects_, coke_position_tolerance_, coke_orientation_tolerance_rad_,
      true);
}

}  // namespace panda_gazebo_demo::pick_place
