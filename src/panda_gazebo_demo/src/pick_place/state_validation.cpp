#include "panda_gazebo_demo/pick_place/state_validation.hpp"

#include <cmath>
#include <utility>

namespace panda_gazebo_demo::pick_place
{

namespace
{

constexpr auto kFinger1 = "panda_finger_joint1";
constexpr auto kFinger2 = "panda_finger_joint2";

std::optional<double> valueFor(
  const std::map<std::string, double> & values,
  const std::string & name)
{
  const auto value = values.find(name);
  if (value == values.end() || !std::isfinite(value->second)) {
    return std::nullopt;
  }
  return value->second;
}

ValidationResult incompleteGripperEvidence()
{
  return {false, {{FailureCategory::GRIPPER, "GRIPPER_EVIDENCE_INCOMPLETE",
      "Both finite finger positions and velocities are required", {}}}, {}};
}

ValidationResult baseResult(const GripperEvidence & evidence)
{
  ValidationResult result{true, {}, {}};
  result.metrics = {{"finger1_position", *evidence.finger1_position},
    {"finger2_position", *evidence.finger2_position},
    {"finger1_velocity", *evidence.finger1_velocity},
    {"finger2_velocity", *evidence.finger2_velocity},
    {"finger_symmetry_error",
      std::abs(*evidence.finger1_position - *evidence.finger2_position)}};
  return result;
}

bool complete(const GripperEvidence & evidence)
{
  return evidence.finger1_position && evidence.finger2_position &&
         evidence.finger1_velocity && evidence.finger2_velocity;
}

bool stopped(const GripperEvidence & evidence, const GripperLimits & limits)
{
  return std::abs(*evidence.finger1_velocity) <= limits.velocity_tolerance &&
         std::abs(*evidence.finger2_velocity) <= limits.velocity_tolerance;
}

}  // namespace

GripperEvidence gripperEvidence(const WorldSnapshot & snapshot)
{
  return {valueFor(snapshot.joint_positions, kFinger1),
    valueFor(snapshot.joint_positions, kFinger2),
    valueFor(snapshot.joint_velocities, kFinger1),
    valueFor(snapshot.joint_velocities, kFinger2)};
}

ValidationResult validateGripperOpen(
  const WorldSnapshot & snapshot, const GripperLimits & limits)
{
  const auto evidence = gripperEvidence(snapshot);
  if (!complete(evidence)) {
    return incompleteGripperEvidence();
  }
  auto result = baseResult(evidence);
  if (*evidence.finger1_position < limits.open_min ||
    *evidence.finger2_position < limits.open_min)
  {
    result.failures.push_back({FailureCategory::GRIPPER, "GRIPPER_NOT_SAFELY_OPEN",
        "Both finger positions must be inside the safe-open range", {}});
  }
  if (!stopped(evidence, limits)) {
    result.failures.push_back({FailureCategory::GRIPPER, "GRIPPER_NOT_STATIONARY",
        "Both finger velocities must be below the stop threshold", {}});
  }
  result.ok = result.failures.empty();
  return result;
}

ValidationResult validateGripperGrasp(
  const WorldSnapshot & snapshot, const GripperLimits & limits)
{
  const auto evidence = gripperEvidence(snapshot);
  if (!complete(evidence)) {
    return incompleteGripperEvidence();
  }
  auto result = baseResult(evidence);
  if (*evidence.finger1_position < limits.grasp_min ||
    *evidence.finger1_position > limits.grasp_max ||
    *evidence.finger2_position < limits.grasp_min ||
    *evidence.finger2_position > limits.grasp_max)
  {
    result.failures.push_back({FailureCategory::GRIPPER,
        "GRIPPER_GRASP_POSITION_OUT_OF_RANGE",
        "Both finger positions must be inside the configured grasp range", {}});
  }
  if (result.metrics.at("finger_symmetry_error") > limits.symmetry_tolerance) {
    result.failures.push_back({FailureCategory::GRIPPER, "GRIPPER_FINGERS_ASYMMETRIC",
        "Finger positions differ by more than the configured tolerance", {}});
  }
  if (!stopped(evidence, limits)) {
    result.failures.push_back({FailureCategory::GRIPPER, "GRIPPER_NOT_STATIONARY",
        "Both finger velocities must be below the stop threshold", {}});
  }
  result.ok = result.failures.empty();
  return result;
}

ValidationResult validateAttachmentState(
  const WorldSnapshot & snapshot, bool gazebo_attached, bool moveit_attached)
{
  if (!snapshot.gazebo_coke_attached || !snapshot.moveit_coke_attached) {
    return {false, {{FailureCategory::WORLD_INCONSISTENCY, "ATTACHMENT_STATE_UNKNOWN",
        "Both Gazebo and MoveIt attachment facts are required", {}}}, {}};
  }
  const std::map<std::string, double> metrics{
    {"gazebo_attached", *snapshot.gazebo_coke_attached ? 1.0 : 0.0},
    {"moveit_attached", *snapshot.moveit_coke_attached ? 1.0 : 0.0},
  };
  if (*snapshot.gazebo_coke_attached != gazebo_attached ||
    *snapshot.moveit_coke_attached != moveit_attached)
  {
    return {false, {{FailureCategory::WORLD_INCONSISTENCY, "ATTACHMENT_STATE_MISMATCH",
        "Gazebo and MoveIt attachment facts do not match the expected combination", {}}},
      metrics};
  }
  return {true, {}, metrics};
}

CokePoseStabilityTracker::CokePoseStabilityTracker(
  std::size_t required_samples, double position_tolerance,
  double orientation_tolerance_rad)
: required_samples_(required_samples), position_tolerance_(position_tolerance),
  orientation_tolerance_rad_(orientation_tolerance_rad)
{
}

void CokePoseStabilityTracker::addSample(
  const Pose3d & pose, std::chrono::steady_clock::time_point observed_at)
{
  samples_.push_back({pose, observed_at});
  while (samples_.size() > required_samples_) {
    samples_.pop_front();
  }
}

std::optional<bool> CokePoseStabilityTracker::stationary() const noexcept
{
  if (required_samples_ < 2 || samples_.size() < required_samples_) {
    return std::nullopt;
  }
  for (std::size_t index = 1; index < samples_.size(); ++index) {
    if (samples_[index].observed_at <= samples_[index - 1].observed_at ||
      positionDistance(samples_[index - 1].pose, samples_[index].pose) > position_tolerance_ ||
      orientationDistance(samples_[index - 1].pose, samples_[index].pose) >
      orientation_tolerance_rad_)
    {
      return false;
    }
  }
  return true;
}

}  // namespace panda_gazebo_demo::pick_place
