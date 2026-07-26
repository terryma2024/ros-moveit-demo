#include "so101_gazebo_demo/pick_place/so101_motion_validation.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <utility>

namespace so101_gazebo_demo::pick_place
{
namespace
{

constexpr double kTiny = 1e-12;

bool finite(double value) { return std::isfinite(value); }

bool finite(const Vec3 & value)
{
  return finite(value.x) && finite(value.y) && finite(value.z);
}

double norm(const Vec3 & value)
{
  return std::sqrt(value.x * value.x + value.y * value.y + value.z * value.z);
}

Vec3 normalized(const Vec3 & value)
{
  const double length = norm(value);
  if (!finite(value) || !finite(length) || length <= kTiny) {
    const double nan = std::numeric_limits<double>::quiet_NaN();
    return {nan, nan, nan};
  }
  return {value.x / length, value.y / length, value.z / length};
}

double dot(const Vec3 & a, const Vec3 & b)
{
  return a.x * b.x + a.y * b.y + a.z * b.z;
}

Vec3 subtract(const Vec3 & a, const Vec3 & b)
{
  return {a.x - b.x, a.y - b.y, a.z - b.z};
}

Vec3 scale(const Vec3 & value, double factor)
{
  return {value.x * factor, value.y * factor, value.z * factor};
}

Vec3 position(const Pose3d & pose) { return {pose.x, pose.y, pose.z}; }

bool finitePose(const Pose3d & pose)
{
  return finite(pose.x) && finite(pose.y) && finite(pose.z) && finite(pose.qx) &&
         finite(pose.qy) && finite(pose.qz) && finite(pose.qw);
}

ValidationResult failure(std::string code, std::string message,
                         std::map<std::string, double> metrics = {})
{
  Failure item{FailureCategory::PLAN_VALIDATION, std::move(code), std::move(message), metrics};
  return {false, {std::move(item)}, std::move(metrics)};
}

ValidationResult validateCommon(const MotionPlanArtifact & plan,
                                const MotionValidationConfig & config)
{
  if (plan.joint_names != config.expected_joint_names) {
    return failure("ARM_JOINT_ORDER_MISMATCH", "Plan must contain SO-101 arm joints in profile order");
  }
  const auto joint_count = config.expected_joint_names.size();
  if (joint_count == 0 || plan.start_joint_positions.size() != joint_count ||
      plan.goal_joint_positions.size() != joint_count) {
    return failure("ARM_JOINT_EVIDENCE_INCOMPLETE", "Plan start and goal joint evidence is incomplete");
  }
  if (!plan.collision_aware) {
    return failure("PLAN_NOT_COLLISION_AWARE", "Motion plan lacks collision-aware evidence");
  }
  if (!plan.time_parameterized) {
    return failure("PLAN_NOT_TIME_PARAMETERIZED", "Motion plan lacks time parameterization");
  }
  if (plan.trajectory_points < 2 || plan.samples.size() != plan.trajectory_points) {
    return failure("MOTION_TRAJECTORY_INCOMPLETE", "Motion plan samples do not cover the trajectory");
  }
  for (double value : plan.start_joint_positions) {
    if (!finite(value)) return failure("NONFINITE_JOINT_EVIDENCE", "Start joint evidence is non-finite");
  }
  for (double value : plan.goal_joint_positions) {
    if (!finite(value)) return failure("NONFINITE_JOINT_EVIDENCE", "Goal joint evidence is non-finite");
  }

  for (std::size_t i = 0; i < plan.samples.size(); ++i) {
    const auto & sample = plan.samples[i];
    if (!finitePose(sample.tcp_pose) || sample.joint_positions.size() != joint_count ||
        !finite(sample.time_from_start_seconds)) {
      return failure("MOTION_SAMPLE_INVALID", "FK sample is missing or non-finite");
    }
    if (!sample.collision_free) {
      return failure("MOTION_SAMPLE_IN_COLLISION", "At least one sampled robot state is in collision",
                     {{"sample_index", static_cast<double>(i)}});
    }
    for (double value : sample.joint_positions) {
      if (!finite(value)) return failure("MOTION_SAMPLE_INVALID", "Joint sample is non-finite");
    }
    if (i > 0 && sample.time_from_start_seconds <=
                   plan.samples[i - 1].time_from_start_seconds) {
      return failure("TRAJECTORY_TIME_NOT_INCREASING", "Trajectory timestamps must strictly increase");
    }
  }
  if (plan.samples.front().time_from_start_seconds < 0.0 ||
      plan.samples.back().time_from_start_seconds < config.min_duration_seconds) {
    return failure("TRAJECTORY_DURATION_TOO_SHORT", "Trajectory duration is below the configured minimum");
  }

  const auto compare_joints = [&](const std::vector<double> & observed,
                                  const std::vector<double> & expected,
                                  const char * code) -> ValidationResult {
    for (std::size_t i = 0; i < joint_count; ++i) {
      if (std::abs(observed[i] - expected[i]) > config.joint_endpoint_tolerance) {
        return failure(code, "Trajectory endpoint does not match its joint evidence",
                       {{"joint_index", static_cast<double>(i)},
                        {"joint_error", std::abs(observed[i] - expected[i])}});
      }
    }
    return {true, {}, {}};
  };
  if (auto result = compare_joints(plan.samples.front().joint_positions,
                                   plan.start_joint_positions, "PLAN_START_JOINT_MISMATCH");
      !result.ok) {
    return result;
  }
  if (auto result = compare_joints(plan.samples.back().joint_positions,
                                   plan.goal_joint_positions, "PLAN_GOAL_JOINT_MISMATCH");
      !result.ok) {
    return result;
  }

  double max_joint_jump = 0.0;
  for (std::size_t i = 1; i < plan.samples.size(); ++i) {
    for (std::size_t j = 0; j < joint_count; ++j) {
      const double jump = std::abs(plan.samples[i].joint_positions[j] -
                                   plan.samples[i - 1].joint_positions[j]);
      max_joint_jump = std::max(max_joint_jump, jump);
      if (jump > config.max_joint_jump) {
        return failure("JOINT_WAYPOINT_JUMP_TOO_LARGE", "Adjacent joint samples exceed jump limit",
                       {{"sample_index", static_cast<double>(i)},
                        {"joint_index", static_cast<double>(j)}, {"joint_jump", jump}});
      }
    }
  }

  const auto endpoint_error = norm(subtract(position(plan.samples.back().tcp_pose),
                                             config.endpoint_position));
  if (!finite(endpoint_error) || endpoint_error > config.position_tolerance) {
    return failure("TCP_ENDPOINT_OUTSIDE_TOLERANCE", "TCP endpoint is outside position tolerance",
                   {{"position_error", endpoint_error}});
  }
  const auto axis_error = approachAxisError(plan.samples.back().tcp_pose,
                                             config.local_approach_axis,
                                             config.target_approach_axis);
  if (!finite(axis_error) || axis_error > config.axis_tolerance_rad) {
    return failure("TCP_AXIS_OUTSIDE_TOLERANCE", "TCP approach axis is outside tolerance",
                   {{"axis_error", axis_error}});
  }
  return {true, {}, {{"position_error", endpoint_error},
                     {"axis_error", axis_error},
                     {"max_joint_jump", max_joint_jump},
                     {"duration_seconds", plan.samples.back().time_from_start_seconds}}};
}

}  // namespace

double approachAxisError(const Pose3d & pose, const Vec3 & local_axis,
                         const Vec3 & target_axis) noexcept
{
  const Vec3 local = normalized(local_axis);
  const Vec3 target = normalized(target_axis);
  const double q_norm = std::sqrt(pose.qx * pose.qx + pose.qy * pose.qy +
                                  pose.qz * pose.qz + pose.qw * pose.qw);
  if (!finitePose(pose) || !finite(local) || !finite(target) || !finite(q_norm) ||
      q_norm <= kTiny) {
    return std::numeric_limits<double>::infinity();
  }
  const double x = pose.qx / q_norm;
  const double y = pose.qy / q_norm;
  const double z = pose.qz / q_norm;
  const double w = pose.qw / q_norm;
  const Vec3 rotated{
    (1.0 - 2.0 * (y * y + z * z)) * local.x + 2.0 * (x * y - z * w) * local.y +
      2.0 * (x * z + y * w) * local.z,
    2.0 * (x * y + z * w) * local.x + (1.0 - 2.0 * (x * x + z * z)) * local.y +
      2.0 * (y * z - x * w) * local.z,
    2.0 * (x * z - y * w) * local.x + 2.0 * (y * z + x * w) * local.y +
      (1.0 - 2.0 * (x * x + y * y)) * local.z};
  const double cosine = std::clamp(dot(normalized(rotated), target), -1.0, 1.0);
  return finite(cosine) ? std::acos(cosine) : std::numeric_limits<double>::infinity();
}

ValidationResult validateJointGoalPlan(const MotionPlanArtifact & plan,
                                       const MotionValidationConfig & config)
{
  return validateCommon(plan, config);
}

ValidationResult validateWaypointLadder(const MotionPlanArtifact & plan,
                                        const MotionValidationConfig & config)
{
  auto common = validateCommon(plan, config);
  if (!common.ok) return common;
  const Vec3 direction = normalized(config.path_direction);
  if (!finite(direction)) {
    return failure("PATH_DIRECTION_INVALID", "Path direction must be finite and non-zero");
  }
  const Vec3 origin = position(plan.samples.front().tcp_pose);
  double previous_progress = 0.0;
  double max_lateral = 0.0;
  double max_axis_error = 0.0;
  for (std::size_t i = 0; i < plan.samples.size(); ++i) {
    const Vec3 delta = subtract(position(plan.samples[i].tcp_pose), origin);
    const double progress = dot(delta, direction);
    const double lateral = norm(subtract(delta, scale(direction, progress)));
    if (i > 0 && progress + config.monotonic_tolerance < previous_progress) {
      return failure("TCP_PATH_NON_MONOTONIC", "TCP path reverses along the requested axis",
                     {{"sample_index", static_cast<double>(i)}, {"progress", progress},
                      {"previous_progress", previous_progress}});
    }
    if (!finite(lateral) || lateral > config.max_lateral_deviation) {
      return failure("TCP_PATH_LATERAL_DEVIATION", "TCP path exceeds lateral deviation tolerance",
                     {{"sample_index", static_cast<double>(i)}, {"lateral_deviation", lateral}});
    }
    const double axis_error = approachAxisError(plan.samples[i].tcp_pose,
                                                config.local_approach_axis,
                                                config.target_approach_axis);
    if (!finite(axis_error) || axis_error > config.axis_tolerance_rad) {
      return failure("TCP_AXIS_OUTSIDE_TOLERANCE", "A waypoint tool axis is outside tolerance",
                     {{"sample_index", static_cast<double>(i)}, {"axis_error", axis_error}});
    }
    previous_progress = progress;
    max_lateral = std::max(max_lateral, lateral);
    max_axis_error = std::max(max_axis_error, axis_error);
  }
  common.metrics["max_lateral_deviation"] = max_lateral;
  common.metrics["max_axis_error"] = max_axis_error;
  common.metrics["axial_progress"] = previous_progress;
  return common;
}

SO101MotionPlanValidator::SO101MotionPlanValidator(MotionValidationConfig config,
                                                   bool require_ladder)
: config_(std::move(config)), require_ladder_(require_ladder)
{
}

ValidationResult SO101MotionPlanValidator::validate(State, const WorldSnapshot &,
                                                    const PlanArtifact & artifact) const
{
  const auto * motion = dynamic_cast<const MotionPlanArtifact *>(&artifact);
  if (!motion) {
    return failure("MOTION_PLAN_ARTIFACT_REQUIRED", "SO-101 motion validator needs FK motion evidence");
  }
  return require_ladder_ ? validateWaypointLadder(*motion, config_)
                         : validateJointGoalPlan(*motion, config_);
}

}  // namespace so101_gazebo_demo::pick_place
