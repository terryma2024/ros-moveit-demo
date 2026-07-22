#include "panda_gazebo_demo/pick_place/cartesian_plan_validation.hpp"
#include "panda_gazebo_demo/pick_place/motion_plan_evidence.hpp"

#include <algorithm>
#include <cmath>
#include <string>

namespace panda_gazebo_demo::pick_place
{

namespace
{

void addFailure(ValidationResult & result, std::string code, std::string message)
{
  result.failures.push_back(
    {FailureCategory::PLAN_VALIDATION, std::move(code), std::move(message), {}});
}

bool poseIsFinite(const Pose3d & pose)
{
  return std::isfinite(pose.x) && std::isfinite(pose.y) && std::isfinite(pose.z) &&
         std::isfinite(pose.qx) && std::isfinite(pose.qy) && std::isfinite(pose.qz) &&
         std::isfinite(pose.qw);
}

void addMotionFailure(ValidationResult & result, std::string code, std::string message)
{
  result.failures.push_back(
    {FailureCategory::PLAN_VALIDATION, std::move(code), std::move(message), {}});
}

}  // namespace

ValidationResult validateMotionStartJoints(
  const std::map<std::string, double> & planned_start_joint_positions,
  const std::map<std::string, double> & observed_joint_positions,
  double tolerance)
{
  ValidationResult result{true, {}, {}};
  if (planned_start_joint_positions.empty()) {
    addMotionFailure(result, "MOTION_START_JOINTS_MISSING",
      "Motion plan does not contain named planned-start joint positions");
  }
  if (!std::isfinite(tolerance) || tolerance <= 0.0) {
    addMotionFailure(result, "MOTION_START_JOINT_TOLERANCE_INVALID",
      "Motion start joint tolerance must be finite and positive");
  }
  double maximum_error = 0.0;
  for (const auto & [name, planned_position] : planned_start_joint_positions) {
    const auto observed = observed_joint_positions.find(name);
    if (observed == observed_joint_positions.end()) {
      addMotionFailure(result, "MOTION_START_JOINTS_MISSING",
        "Observed world snapshot is missing planned joint " + name);
      continue;
    }
    if (!std::isfinite(planned_position) || !std::isfinite(observed->second)) {
      addMotionFailure(result, "MOTION_START_JOINT_NON_FINITE",
        "Planned or observed start position is non-finite for joint " + name);
      continue;
    }
    const double error = std::abs(planned_position - observed->second);
    maximum_error = std::max(maximum_error, error);
    if (std::isfinite(tolerance) && tolerance > 0.0 && error > tolerance) {
      addMotionFailure(result, "MOTION_START_JOINT_MISMATCH",
        "Observed start position differs from the plan for joint " + name);
    }
  }
  result.metrics["motion_start_joint_max_error"] = maximum_error;
  result.ok = result.failures.empty();
  return result;
}

ValidationResult validateCartesianPlan(
  const CartesianPlanEvidence & evidence, const Pose3d & target,
  const CartesianPlanLimits & limits)
{
  ValidationResult result{true, {}, {}};
  result.metrics["cartesian_fraction"] = evidence.fraction;
  result.metrics["trajectory_points"] = static_cast<double>(evidence.trajectory_points);
  result.metrics["max_joint_delta"] = evidence.max_joint_delta;

  if (!std::isfinite(evidence.fraction) || evidence.fraction < limits.min_fraction) {
    addFailure(result, "CARTESIAN_FRACTION_BELOW_THRESHOLD",
      "Cartesian path fraction is below the configured minimum");
  }
  if (evidence.trajectory_points == 0 || evidence.tcp_path.empty()) {
    addFailure(result, "EMPTY_CARTESIAN_TRAJECTORY",
      "Cartesian planning returned an empty trajectory");
  } else if (evidence.tcp_path.size() != evidence.trajectory_points) {
    addFailure(result, "CARTESIAN_TCP_PATH_UNAVAILABLE",
      "TCP forward kinematics are unavailable for one or more trajectory points");
  }
  if (!evidence.time_parameterized) {
    addFailure(result, "CARTESIAN_TRAJECTORY_NOT_TIME_PARAMETERIZED",
      "Cartesian trajectory timestamps must increase before execution");
  }
  if (!std::isfinite(evidence.max_joint_delta) ||
    evidence.max_joint_delta > limits.max_joint_delta)
  {
    addFailure(result, "CARTESIAN_JOINT_JUMP_EXCEEDED",
      "An adjacent Cartesian trajectory joint change exceeds the configured threshold");
  }

  const auto tcp_path_finite = poseIsFinite(evidence.start_tcp_pose) && poseIsFinite(target) &&
    std::all_of(evidence.tcp_path.begin(), evidence.tcp_path.end(), poseIsFinite);
  if (!tcp_path_finite) {
    addFailure(result, "CARTESIAN_TCP_PATH_NON_FINITE",
      "Cartesian trajectory contains a non-finite TCP pose");
  }

  double max_lateral_deviation = 0.0;
  double max_orientation_error = 0.0;
  bool monotonic_descent = true;
  auto previous_z = evidence.start_tcp_pose.z;
  if (tcp_path_finite) {
    for (const auto & pose : evidence.tcp_path) {
      const auto lateral_deviation = std::hypot(
        pose.x - evidence.start_tcp_pose.x, pose.y - evidence.start_tcp_pose.y);
      max_lateral_deviation = std::max(max_lateral_deviation, lateral_deviation);
      max_orientation_error = std::max(max_orientation_error, orientationDistance(pose, target));
      if (pose.z > previous_z + 1.0e-4) {
        monotonic_descent = false;
      }
      previous_z = pose.z;
    }
  }
  result.metrics["max_lateral_deviation"] = max_lateral_deviation;
  result.metrics["max_orientation_error_rad"] = max_orientation_error;
  if (max_lateral_deviation > limits.max_lateral_deviation) {
    addFailure(result, "CARTESIAN_LATERAL_DEVIATION_EXCEEDED",
      "Cartesian descent deviates laterally beyond the configured tolerance");
  }
  if (!monotonic_descent) {
    addFailure(result, "CARTESIAN_PATH_NOT_MONOTONIC_DESCENT",
      "Cartesian descent contains upward TCP motion");
  }
  if (max_orientation_error > limits.max_orientation_error_rad) {
    addFailure(result, "CARTESIAN_ORIENTATION_DEVIATION_EXCEEDED",
      "Cartesian descent does not preserve the configured grasp orientation");
  }

  if (tcp_path_finite && !evidence.tcp_path.empty()) {
    const auto endpoint_position_error = positionDistance(evidence.tcp_path.back(), target);
    const auto endpoint_orientation_error = orientationDistance(evidence.tcp_path.back(), target);
    result.metrics["planned_tcp_position_error"] = endpoint_position_error;
    result.metrics["planned_tcp_orientation_error_rad"] = endpoint_orientation_error;
    if (endpoint_position_error > limits.endpoint_position_tolerance) {
      addFailure(result, "CARTESIAN_ENDPOINT_POSITION_OUTSIDE_TOLERANCE",
        "Cartesian trajectory endpoint does not reach the target position");
    }
    if (endpoint_orientation_error > limits.endpoint_orientation_tolerance_rad) {
      addFailure(result, "CARTESIAN_ENDPOINT_ORIENTATION_OUTSIDE_TOLERANCE",
        "Cartesian trajectory endpoint does not reach the target orientation");
    }
  }
  result.ok = result.failures.empty();
  return result;
}

ValidationResult validateMotionPlan(
  const MotionPlanEvidence & evidence, const Pose3d & target,
  MotionKind expected_kind, bool expected_carrying,
  const MotionPlanLimits & limits)
{
  ValidationResult result{true, {}, {}};
  result.metrics["cartesian_fraction"] = evidence.cartesian_fraction;
  result.metrics["trajectory_points"] = static_cast<double>(evidence.trajectory_points);
  result.metrics["duration_seconds"] = evidence.duration_seconds;
  result.metrics["max_joint_jump"] = evidence.max_joint_jump;

  if (evidence.kind != expected_kind || evidence.carrying != expected_carrying) {
    addMotionFailure(result, "MOTION_EVIDENCE_CONFIGURATION_MISMATCH",
      "Motion plan evidence does not match the configured motion kind and carrying mode");
  }
  if (evidence.trajectory_points == 0 || evidence.tcp_path.empty()) {
    addMotionFailure(result, "EMPTY_MOTION_TRAJECTORY",
      "Motion planning returned an empty trajectory");
  } else if (evidence.tcp_path.size() != evidence.trajectory_points) {
    addMotionFailure(result, "MOTION_TCP_PATH_UNAVAILABLE",
      "TCP forward kinematics are unavailable for one or more trajectory points");
  }
  if (!std::isfinite(evidence.duration_seconds) || evidence.duration_seconds <= 0.0) {
    addMotionFailure(result, "MOTION_TRAJECTORY_NOT_TIMED",
      "Motion trajectory must have a positive time-parameterized duration");
  }
  if (!std::isfinite(evidence.max_joint_jump) ||
    evidence.max_joint_jump > limits.max_joint_jump)
  {
    addMotionFailure(result, "MOTION_JOINT_JUMP_EXCEEDED",
      "An adjacent trajectory joint change exceeds the configured threshold");
  }
  if (!evidence.collision_aware) {
    addMotionFailure(result, "COLLISION_AWARE_PLAN_EVIDENCE_MISSING",
      "Motion plan must be produced with collision checking enabled");
  }

  const bool poses_finite = poseIsFinite(evidence.start_tcp_pose) &&
    poseIsFinite(evidence.end_tcp_pose) && poseIsFinite(target) &&
    std::all_of(evidence.tcp_path.begin(), evidence.tcp_path.end(), poseIsFinite);
  if (!poses_finite) {
    addMotionFailure(result, "MOTION_TCP_PATH_NON_FINITE",
      "Motion trajectory contains a non-finite TCP pose");
  }

  double max_lateral_deviation = 0.0;
  double max_orientation_error = 0.0;
  bool monotonic_up = true;
  bool monotonic_down = true;
  double previous_z = evidence.start_tcp_pose.z;
  if (poses_finite) {
    for (const auto & pose : evidence.tcp_path) {
      max_lateral_deviation = std::max(max_lateral_deviation,
        std::hypot(pose.x - evidence.start_tcp_pose.x,
          pose.y - evidence.start_tcp_pose.y));
      max_orientation_error = std::max(
        max_orientation_error, orientationDistance(pose, target));
      if (pose.z < previous_z - 1.0e-4) {
        monotonic_up = false;
      }
      if (pose.z > previous_z + 1.0e-4) {
        monotonic_down = false;
      }
      previous_z = pose.z;
    }
  }
  result.metrics["max_lateral_deviation"] = max_lateral_deviation;
  result.metrics["max_orientation_error_rad"] = max_orientation_error;
  if (expected_kind != MotionKind::POSE) {
    if (!std::isfinite(evidence.cartesian_fraction) ||
      evidence.cartesian_fraction < limits.min_cartesian_fraction)
    {
      addMotionFailure(result, "CARTESIAN_FRACTION_BELOW_THRESHOLD",
        "Cartesian path fraction is below the configured minimum");
    }
    if (max_lateral_deviation > limits.max_lateral_deviation) {
      addMotionFailure(result, "CARTESIAN_LATERAL_DEVIATION_EXCEEDED",
        "Cartesian path deviates laterally beyond the configured tolerance");
    }
    if (expected_kind == MotionKind::CARTESIAN_UP && !monotonic_up) {
      addMotionFailure(result, "CARTESIAN_PATH_NOT_MONOTONIC_UP",
        "Cartesian upward path contains a downward TCP segment");
    }
    if (expected_kind == MotionKind::CARTESIAN_DOWN && !monotonic_down) {
      addMotionFailure(result, "CARTESIAN_PATH_NOT_MONOTONIC_DOWN",
        "Cartesian downward path contains an upward TCP segment");
    }
  }
  if (max_orientation_error > limits.max_orientation_error_rad) {
    addMotionFailure(result, "MOTION_ORIENTATION_DEVIATION_EXCEEDED",
      "Motion path does not preserve the configured TCP orientation");
  }

  if (poses_finite && !evidence.tcp_path.empty()) {
    const double endpoint_position_error = positionDistance(evidence.end_tcp_pose, target);
    const double endpoint_orientation_error = orientationDistance(evidence.end_tcp_pose, target);
    const double fk_endpoint_position_error =
      positionDistance(evidence.tcp_path.back(), evidence.end_tcp_pose);
    const double fk_endpoint_orientation_error =
      orientationDistance(evidence.tcp_path.back(), evidence.end_tcp_pose);
    result.metrics["planned_tcp_position_error"] = endpoint_position_error;
    result.metrics["planned_tcp_orientation_error_rad"] = endpoint_orientation_error;
    result.metrics["fk_endpoint_position_error"] = fk_endpoint_position_error;
    result.metrics["fk_endpoint_orientation_error_rad"] = fk_endpoint_orientation_error;
    if (endpoint_position_error > limits.endpoint_position_tolerance ||
      fk_endpoint_position_error > limits.endpoint_position_tolerance)
    {
      addMotionFailure(result, "MOTION_ENDPOINT_POSITION_OUTSIDE_TOLERANCE",
        "Motion trajectory endpoint does not reach its target position");
    }
    if (endpoint_orientation_error > limits.endpoint_orientation_tolerance_rad ||
      fk_endpoint_orientation_error > limits.endpoint_orientation_tolerance_rad)
    {
      addMotionFailure(result, "MOTION_ENDPOINT_ORIENTATION_OUTSIDE_TOLERANCE",
        "Motion trajectory endpoint does not reach its target orientation");
    }
  }

  result.metrics["attached_object_in_model"] = evidence.attached_object_in_model ? 1.0 : 0.0;
  result.metrics["max_carried_relative_position_error"] =
    evidence.max_carried_relative_position_error;
  result.metrics["max_carried_relative_orientation_error_rad"] =
    evidence.max_carried_relative_orientation_error_rad;
  result.metrics["carried_clearance_verified"] =
    evidence.carried_clearance_verified ? 1.0 : 0.0;
  if (expected_carrying) {
    if (!evidence.attached_object_in_model) {
      addMotionFailure(result, "ATTACHED_OBJECT_MODEL_EVIDENCE_MISSING",
        "Carried motion plan does not contain the attached Coke collision model");
    }
    if (!evidence.carried_relative_pose_available) {
      addMotionFailure(result, "CARRIED_RELATIVE_POSE_EVIDENCE_MISSING",
        "Carried motion plan does not contain TCP-to-Coke relative-pose evidence");
    }
    if (!std::isfinite(evidence.max_carried_relative_position_error) ||
      evidence.max_carried_relative_position_error >
      limits.carried_relative_position_tolerance)
    {
      addMotionFailure(result, "CARRIED_RELATIVE_POSITION_DRIFT",
        "Planned TCP-to-Coke relative position exceeds tolerance");
    }
    if (!std::isfinite(evidence.max_carried_relative_orientation_error_rad) ||
      evidence.max_carried_relative_orientation_error_rad >
      limits.carried_relative_orientation_tolerance_rad)
    {
      addMotionFailure(result, "CARRIED_RELATIVE_ORIENTATION_DRIFT",
        "Planned TCP-to-Coke relative orientation exceeds tolerance");
    }
    if (!evidence.carried_clearance_verified) {
      addMotionFailure(result, "CARRIED_OBJECT_CLEARANCE_EVIDENCE_MISSING",
        "Carried motion was not collision-checked with the attached Coke model");
    }
  }

  result.ok = result.failures.empty();
  return result;
}

MotionPlanValidator::MotionPlanValidator(
  MotionStateConfig config,
  std::shared_ptr<const PickPlaceTargetPolicy> target_policy,
  MotionPlanLimits limits)
: config_(config), target_policy_(std::move(target_policy)), limits_(limits)
{
}

ValidationResult MotionPlanValidator::validate(
  State state, const WorldSnapshot & before,
  const PlanArtifact & artifact) const
{
  if (state != config_.state) {
    return {false, {{FailureCategory::PLAN_VALIDATION, "MOTION_VALIDATOR_STATE_MISMATCH",
        "Motion plan validator received a state other than its configured state", {}}}, {}};
  }
  const auto * evidence = dynamic_cast<const MotionPlanEvidence *>(&artifact);
  if (evidence == nullptr || evidence->state != config_.state ||
    evidence->next_state != config_.next_state)
  {
    return {false, {{FailureCategory::PLAN_VALIDATION, "INVALID_MOTION_PLAN_ARTIFACT",
        "Motion plan validator requires typed evidence for its configured transition", {}}}, {}};
  }
  if (!target_policy_) {
    return {false, {{FailureCategory::CONFIGURATION, "TARGET_POLICY_MISSING",
        "Motion plan validator requires a target policy", {}}}, {}};
  }
  auto result = validateMotionStartJoints(
    evidence->planned_start_joint_positions, before.joint_positions,
    limits_.start_joint_tolerance);
  if (!result.ok) {
    return result;
  }
  const ObservationResult observation{before, std::nullopt};
  const auto target = target_policy_->targetPose(
    config_.state, config_.next_state, observation);
  if (!target.target_pose) {
    return {false, {target.failure.value_or(Failure{FailureCategory::CONFIGURATION,
            "TARGET_POLICY_FAILED", "Target policy did not return a validation target", {}})}, {}};
  }
  return validateMotionPlan(
    *evidence, *target.target_pose, config_.kind, config_.carrying, limits_);
}

}  // namespace panda_gazebo_demo::pick_place
