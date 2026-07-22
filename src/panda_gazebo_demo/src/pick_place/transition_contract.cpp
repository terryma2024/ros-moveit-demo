#include "panda_gazebo_demo/pick_place/transition_contract.hpp"

#include <utility>

#include "panda_gazebo_demo/pick_place/transition_table.hpp"

namespace panda_gazebo_demo::pick_place
{

namespace
{

void addFailure(
  ValidationResult & result, FailureCategory category, std::string code, std::string message)
{
  result.failures.push_back({category, std::move(code), std::move(message), {}});
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
  TransitionKey key, const WorldSnapshot & before, const WorldSnapshot & after,
  const ActionResult & action_result) const
{
  const auto found = contracts_.find(key);
  if (found == contracts_.end() || !found->second) {
    return {false, {{FailureCategory::CONFIGURATION, "MISSING_TRANSITION_CONTRACT",
        std::string("No execute transition contract registered for ") + toString(key.from) +
        " -> " + toString(key.to), {}}}, {}};
  }
  return found->second->validate(before, after, action_result);
}

ValidationResult TransitionContractRegistry::validatePrecondition(
  TransitionKey key, const WorldSnapshot & before) const
{
  const auto found = contracts_.find(key);
  if (found == contracts_.end() || !found->second) {
    return {false, {{FailureCategory::CONFIGURATION, "MISSING_TRANSITION_CONTRACT",
        std::string("No execute transition contract registered for ") + toString(key.from) +
        " -> " + toString(key.to), {}}}, {}};
  }
  return found->second->validatePrecondition(before);
}

std::optional<Failure> TransitionContractRegistry::validateExecuteCoverage(
  const TransitionTable & table) const
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

MoveAboveObjectContract::MoveAboveObjectContract(
  Pose3d target_pose, std::vector<std::string> required_world_objects,
  double tcp_position_tolerance, double coke_position_tolerance)
: target_pose_(target_pose), required_world_objects_(std::move(required_world_objects)),
  tcp_position_tolerance_(tcp_position_tolerance),
  coke_position_tolerance_(coke_position_tolerance)
{
}

ValidationResult MoveAboveObjectContract::validate(
  const WorldSnapshot & before, const WorldSnapshot & after,
  const ActionResult & action_result) const
{
  ValidationResult result{true, {}, {}};
  if (action_result.status != ActionStatus::SUCCEEDED) {
    addFailure(result, FailureCategory::EXECUTION, "MOVE_ABOVE_EXECUTION_FAILED",
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
  if (after.coke_attached) {
    addFailure(result, FailureCategory::WORLD_INCONSISTENCY, "COKE_UNEXPECTEDLY_ATTACHED",
      "Coke must remain detached after MOVE_ABOVE_OBJECT");
  }
  const auto tcp_error = positionDistance(after.tcp_pose_world, target_pose_);
  result.metrics["tcp_position_error"] = tcp_error;
  if (tcp_error > tcp_position_tolerance_) {
    addFailure(result, FailureCategory::POSTCONDITION, "TCP_OUTSIDE_PREGRASP_TOLERANCE",
      "TCP did not reach the configured pre-grasp position tolerance");
  }
  for (const auto & object_id : required_world_objects_) {
    if (after.world_object_poses.count(object_id) == 0) {
      addFailure(result, FailureCategory::MOVEIT_SCENE, "REQUIRED_WORLD_OBJECT_MISSING",
        "Required Planning Scene world object is missing: " + object_id);
    }
  }
  const auto before_coke = before.world_object_poses.find("coke");
  const auto after_coke = after.world_object_poses.find("coke");
  if (before_coke == before.world_object_poses.end() ||
    after_coke == after.world_object_poses.end())
  {
    addFailure(result, FailureCategory::MOVEIT_SCENE, "COKE_POSE_UNAVAILABLE",
      "Coke world pose is required for post-execution stability validation");
  } else {
    const auto coke_error = positionDistance(before_coke->second, after_coke->second);
    result.metrics["coke_position_drift"] = coke_error;
    if (coke_error > coke_position_tolerance_) {
      addFailure(result, FailureCategory::POSTCONDITION, "COKE_MOVED_DURING_MOVE_ABOVE",
        "Coke moved farther than the configured stability tolerance");
    }
  }
  result.ok = result.failures.empty();
  return result;
}

ValidationResult MoveAboveObjectContract::validatePrecondition(const WorldSnapshot & before) const
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
  if (before.coke_attached) {
    addFailure(result, FailureCategory::WORLD_INCONSISTENCY, "COKE_UNEXPECTEDLY_ATTACHED",
      "Coke must be detached before MOVE_ABOVE_OBJECT");
  }
  for (const auto & object_id : required_world_objects_) {
    if (before.world_object_poses.count(object_id) == 0) {
      addFailure(result, FailureCategory::MOVEIT_SCENE, "REQUIRED_WORLD_OBJECT_MISSING",
        "Required Planning Scene world object is missing: " + object_id);
    }
  }
  if (before.world_object_poses.count("coke") == 0) {
    addFailure(result, FailureCategory::MOVEIT_SCENE, "COKE_POSE_UNAVAILABLE",
      "Coke world pose is required before MOVE_ABOVE_OBJECT");
  }
  result.ok = result.failures.empty();
  return result;
}

}  // namespace panda_gazebo_demo::pick_place
