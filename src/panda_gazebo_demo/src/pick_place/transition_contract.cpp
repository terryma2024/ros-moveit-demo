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

void addBoundaryMetrics(
  std::map<std::string, double> & metrics, const char * prefix,
  const WorldSnapshot & snapshot)
{
  const std::string key_prefix(prefix);
  metrics[key_prefix + "fresh"] = snapshot.fresh ? 1.0 : 0.0;
  metrics[key_prefix + "arm_stationary"] = snapshot.arm_stationary ? 1.0 : 0.0;
  metrics[key_prefix + "gripper_open"] = snapshot.gripper_open ? 1.0 : 0.0;
  metrics[key_prefix + "gazebo_attached"] = snapshot.gazebo_coke_attached ?
    (*snapshot.gazebo_coke_attached ? 1.0 : 0.0) : -1.0;
  metrics[key_prefix + "moveit_attached"] = snapshot.moveit_coke_attached ?
    (*snapshot.moveit_coke_attached ? 1.0 : 0.0) : -1.0;
  for (const auto * joint_name : {"panda_finger_joint1", "panda_finger_joint2"}) {
    const auto position = snapshot.joint_positions.find(joint_name);
    const auto velocity = snapshot.joint_velocities.find(joint_name);
    if (position != snapshot.joint_positions.end()) {
      metrics[key_prefix + joint_name + "_position"] = position->second;
    }
    if (velocity != snapshot.joint_velocities.end()) {
      metrics[key_prefix + joint_name + "_velocity"] = velocity->second;
    }
  }
}

ValidationResult withBoundaryFailureMetrics(
  ValidationResult result, const WorldSnapshot & before,
  const WorldSnapshot * after = nullptr)
{
  addBoundaryMetrics(result.metrics, "before_", before);
  if (after != nullptr) {
    addBoundaryMetrics(result.metrics, "after_", *after);
  }
  for (auto & failure : result.failures) {
    failure.metrics.insert(result.metrics.begin(), result.metrics.end());
  }
  return result;
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
  const auto found = contracts_.find(key);
  return found != contracts_.end() && static_cast<bool>(found->second);
}

ValidationResult TransitionContractRegistry::validate(
  TransitionKey key,
  const WorldSnapshot & before,
  const WorldSnapshot & after,
  const ActionResult & action_result) const
{
  const auto found = contracts_.find(key);
  if (found == contracts_.end() || !found->second) {
    ValidationResult missing{false, {{FailureCategory::CONFIGURATION,
        "MISSING_TRANSITION_CONTRACT",
        std::string("No execute transition contract registered for ") + toString(key.from) +
        " -> " + toString(key.to), {}}}, {}};
    return withBoundaryFailureMetrics(std::move(missing), before, &after);
  }
  return withBoundaryFailureMetrics(
    found->second->validate(before, after, action_result), before, &after);
}

ValidationResult
TransitionContractRegistry::validatePrecondition(
  TransitionKey key,
  const WorldSnapshot & before) const
{
  const auto found = contracts_.find(key);
  if (found == contracts_.end() || !found->second) {
    ValidationResult missing{false, {{FailureCategory::CONFIGURATION,
        "MISSING_TRANSITION_CONTRACT",
        std::string("No execute transition contract registered for ") + toString(key.from) +
        " -> " + toString(key.to), {}}}, {}};
    return withBoundaryFailureMetrics(std::move(missing), before);
  }
  return withBoundaryFailureMetrics(found->second->validatePrecondition(before), before);
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
    if (!isForwardAction(from) || from == State::IDLE || isTerminal(from)) {
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
               "Coke must remain detached after the motion state");
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
    const auto coke_position_drift = positionDistance(
      *before.gazebo_coke_pose_world, *after.gazebo_coke_pose_world);
    const auto coke_orientation_drift = orientationDistance(
      *before.gazebo_coke_pose_world, *after.gazebo_coke_pose_world);
    result.metrics["coke_position_drift"] = coke_position_drift;
    result.metrics["coke_orientation_drift_rad"] = coke_orientation_drift;
    if (coke_position_drift > coke_position_tolerance) {
      addFailure(result, FailureCategory::POSTCONDITION, "COKE_MOVED_DURING_MOTION",
                 "Coke position changed beyond the configured stability tolerance");
    }
    if (coke_orientation_drift > coke_orientation_tolerance_rad) {
      addFailure(result, FailureCategory::POSTCONDITION, "COKE_ROTATED_DURING_MOTION",
                 "Coke orientation changed beyond the configured stability tolerance");
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
               "Arm must be stationary before the configured motion state");
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
               "Coke must be detached before the configured motion state");
  }
  for (const auto & object_id : required_world_objects) {
    if (before.moveit_world_object_poses.count(object_id) == 0) {
      addFailure(result, FailureCategory::MOVEIT_SCENE, "REQUIRED_WORLD_OBJECT_MISSING",
                 "Required Planning Scene world object is missing: " + object_id);
    }
  }
  if (!before.gazebo_coke_pose_world) {
    addFailure(result, FailureCategory::MOVEIT_SCENE, "COKE_POSE_UNAVAILABLE",
               "Coke world pose is required before the configured motion state");
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
  std::shared_ptr<const PickPlaceTargetPolicy> target_policy,
  std::vector<std::string> required_world_objects,
  double tcp_position_tolerance, double tcp_orientation_tolerance_rad,
  double coke_position_tolerance, double coke_orientation_tolerance_rad)
: target_policy_(std::move(target_policy)),
  required_world_objects_(std::move(required_world_objects)),
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
  if (!target_policy_) {
    return {false, {Failure{FailureCategory::CONFIGURATION, "TARGET_POLICY_MISSING",
          "MoveAboveObjectToDescendValidator requires a target policy", {}}}, {}};
  }
  const auto target = target_policy_->targetPose(
    State::MOVE_ABOVE_OBJECT, State::DESCEND, ObservationResult{before, std::nullopt});
  if (!target.target_pose) {
    return {false, {target.failure.value_or(Failure{FailureCategory::CONFIGURATION,
            "TARGET_POLICY_FAILED", "Target policy did not return a MOVE_ABOVE_OBJECT pose", {}})},
      {}};
  }
  return validateMotionCompletion(
    before, after, action_result, *target.target_pose, required_world_objects_,
      tcp_position_tolerance_,
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
  std::shared_ptr<const PickPlaceTargetPolicy> target_policy,
  std::vector<std::string> required_world_objects,
  double tcp_position_tolerance, double tcp_orientation_tolerance_rad,
  double coke_position_tolerance, double coke_orientation_tolerance_rad)
: target_policy_(std::move(target_policy)),
  required_world_objects_(std::move(required_world_objects)),
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
  if (!target_policy_) {
    return {false, {Failure{FailureCategory::CONFIGURATION, "TARGET_POLICY_MISSING",
          "DescendToCloseGripperValidator requires a target policy", {}}}, {}};
  }
  const auto target = target_policy_->targetPose(
    State::DESCEND, State::CLOSE_GRIPPER, ObservationResult{before, std::nullopt});
  if (!target.target_pose) {
    return {false, {target.failure.value_or(Failure{FailureCategory::CONFIGURATION,
            "TARGET_POLICY_FAILED", "Target policy did not return a DESCEND pose", {}})}, {}};
  }
  return validateMotionCompletion(
    before, after, action_result, *target.target_pose, required_world_objects_,
      tcp_position_tolerance_,
    tcp_orientation_tolerance_rad_, coke_position_tolerance_, coke_orientation_tolerance_rad_,
      true);
}

ValidationResult DescendToCloseGripperValidator::validatePrecondition(
  const WorldSnapshot & before) const
{
  auto result = validateMotionPrecondition(
    before, required_world_objects_, coke_position_tolerance_, coke_orientation_tolerance_rad_,
      true);
  if (!target_policy_) {
    addFailure(result, FailureCategory::CONFIGURATION, "TARGET_POLICY_MISSING",
      "DescendToCloseGripperValidator requires a target policy");
    result.ok = false;
    return result;
  }
  const auto start_target = target_policy_->targetPose(
    State::MOVE_ABOVE_OBJECT, State::DESCEND, ObservationResult{before, std::nullopt});
  if (!start_target.target_pose) {
    result.failures.push_back(start_target.failure.value_or(Failure{
        FailureCategory::CONFIGURATION, "TARGET_POLICY_FAILED",
        "Target policy did not return a DESCEND start pose", {}}));
    result.ok = false;
    return result;
  }
  const auto tcp_position_error = positionDistance(before.tcp_pose_world,
      *start_target.target_pose);
  const auto tcp_orientation_error = orientationDistance(
    before.tcp_pose_world, *start_target.target_pose);
  result.metrics["tcp_position_error"] = tcp_position_error;
  result.metrics["tcp_orientation_error_rad"] = tcp_orientation_error;
  if (tcp_position_error > tcp_position_tolerance_) {
    addFailure(result, FailureCategory::PRECONDITION, "TCP_OUTSIDE_DESCEND_START_TOLERANCE",
      "TCP must be at the MOVE_ABOVE_OBJECT target before DESCEND planning");
  }
  if (tcp_orientation_error > tcp_orientation_tolerance_rad_) {
    addFailure(result, FailureCategory::PRECONDITION,
      "TCP_ORIENTATION_OUTSIDE_DESCEND_START_TOLERANCE",
      "TCP orientation must match the MOVE_ABOVE_OBJECT target before DESCEND planning");
  }
  result.ok = result.failures.empty();
  return result;
}

}  // namespace panda_gazebo_demo::pick_place
