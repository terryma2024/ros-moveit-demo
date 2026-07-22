#include "panda_gazebo_demo/pick_place/cartesian_plan_validation.hpp"

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

}  // namespace

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

}  // namespace panda_gazebo_demo::pick_place
