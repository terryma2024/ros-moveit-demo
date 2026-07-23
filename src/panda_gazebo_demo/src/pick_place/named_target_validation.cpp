#include "panda_gazebo_demo/pick_place/named_target_validation.hpp"

#include <cmath>
#include <utility>

namespace panda_gazebo_demo::pick_place
{
namespace
{

void addFailure(ValidationResult & result, std::string code, std::string message)
{
  result.failures.push_back(
    {FailureCategory::PLAN_VALIDATION, std::move(code), std::move(message), {}});
}

ValidationResult finish(ValidationResult result)
{
  result.ok = result.failures.empty();
  return result;
}

bool sameTarget(
  const std::map<std::string, double> & actual,
  const std::map<std::string, double> & expected)
{
  if (actual.size() != expected.size()) {
    return false;
  }
  for (const auto & [joint, expected_position] : expected) {
    const auto it = actual.find(joint);
    if (it == actual.end() || !std::isfinite(expected_position) ||
      !std::isfinite(it->second) || std::abs(it->second - expected_position) > 1.0e-9)
    {
      return false;
    }
  }
  return true;
}

}  // namespace

ValidationResult validateNamedJointTarget(
  const WorldSnapshot & snapshot,
  const std::map<std::string, double> & target_joint_positions,
  double tolerance)
{
  ValidationResult result;
  if (!std::isfinite(tolerance) || tolerance <= 0.0 || target_joint_positions.empty()) {
    addFailure(result, "NAMED_TARGET_MISMATCH",
      "Named target validation requires a nonempty target and positive tolerance");
    return finish(std::move(result));
  }
  for (const auto & [joint, target_position] : target_joint_positions) {
    const auto observed = snapshot.joint_positions.find(joint);
    if (observed == snapshot.joint_positions.end() || !std::isfinite(target_position) ||
      !std::isfinite(observed->second))
    {
      addFailure(result, "NAMED_TARGET_JOINTS_MISSING",
        "Observed named-target joint is missing or non-finite: " + joint);
      continue;
    }
    const double error = std::abs(observed->second - target_position);
    result.metrics["named_target_joint_error_" + joint] = error;
    if (error > tolerance) {
      addFailure(result, "NAMED_TARGET_ENDPOINT_MISMATCH",
        "Observed joint is outside named-target tolerance: " + joint);
    }
  }
  return finish(std::move(result));
}

NamedTargetPlanValidator::NamedTargetPlanValidator(
  State state, State next_state, std::string named_target,
  std::map<std::string, double> target_joint_positions, double joint_tolerance)
: state_(state), next_state_(next_state), named_target_(std::move(named_target)),
  target_joint_positions_(std::move(target_joint_positions)), joint_tolerance_(joint_tolerance)
{
}

ValidationResult NamedTargetPlanValidator::validate(
  State state, const WorldSnapshot & before, const PlanArtifact & artifact) const
{
  static_cast<void>(before);
  ValidationResult result;
  const auto * evidence = dynamic_cast<const MotionPlanEvidence *>(&artifact);
  if (evidence == nullptr) {
    addFailure(result, "INVALID_NAMED_TARGET_PLAN_ARTIFACT",
      "Named-target plan validation requires MotionPlanEvidence");
    return finish(std::move(result));
  }
  if (state != state_ || evidence->state != state_ || evidence->next_state != next_state_ ||
    evidence->kind != MotionKind::NAMED_TARGET || !evidence->named_target ||
    *evidence->named_target != named_target_ ||
    !sameTarget(evidence->target_joint_positions, target_joint_positions_))
  {
    addFailure(result, "NAMED_TARGET_MISMATCH",
      "Named-target plan does not match the configured transition or target");
  }
  if (evidence->trajectory_points == 0) {
    addFailure(result, "NAMED_TARGET_TRAJECTORY_EMPTY",
      "Named-target plan trajectory must contain at least one point");
  }
  WorldSnapshot endpoint_snapshot;
  endpoint_snapshot.joint_positions = evidence->planned_end_joint_positions;
  const auto endpoint = validateNamedJointTarget(
    endpoint_snapshot, target_joint_positions_, joint_tolerance_);
  result.metrics.insert(endpoint.metrics.begin(), endpoint.metrics.end());
  result.failures.insert(result.failures.end(), endpoint.failures.begin(), endpoint.failures.end());
  return finish(std::move(result));
}

}  // namespace panda_gazebo_demo::pick_place
