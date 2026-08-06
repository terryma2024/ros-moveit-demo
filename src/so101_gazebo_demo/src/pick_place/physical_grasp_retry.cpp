#include "so101_gazebo_demo/pick_place/physical_grasp_retry.hpp"

#include <algorithm>
#include <cmath>
#include <string>

namespace so101_gazebo_demo::pick_place
{
namespace
{
Failure rejection(std::string code, std::string message)
{
  return {FailureCategory::POSTCONDITION, std::move(code), std::move(message), {}};
}
}  // namespace

PhysicalGraspRetryDecision decidePhysicalGraspRetry(const PhysicalGraspRetryConfig & config,
                                                    const SO101Profile & profile,
                                                    const PhysicalGraspRetryProgress & current,
                                                    const PhysicalGraspResult & physical_result,
                                                    const WorldSnapshot & after)
{
  PhysicalGraspRetryDecision decision{false, current, std::nullopt};
  if (config.max_attempts != 5 || config.contact_missing_tighten_step_q6 != 0.001 ||
      config.max_tighten_q6 != 0.004 || current.attempt_index == 0 ||
      current.attempt_index > config.max_attempts ||
      current.contact_missing_count >= config.max_attempts ||
      !std::isfinite(current.current_reclose_target_q6)) {
    decision.rejection = rejection("PHYSICAL_GRASP_RETRY_CONFIG_INVALID",
                                   "Physical-grasp retry configuration is invalid");
    return decision;
  }
  if (physical_result.passed || current.attempt_index >= config.max_attempts)
    return decision;

  const bool retryable_code = physical_result.failure.code == "PHYSICAL_GRASP_TABLE_CLEARANCE" ||
                              physical_result.failure.code == "PHYSICAL_GRASP_FOLLOW_RATIO" ||
                              physical_result.failure.code == "PHYSICAL_GRASP_CONTACT_MISSING";
  const bool detached =
    after.gazebo_task_object_attached.has_value() && !*after.gazebo_task_object_attached &&
    after.moveit_task_object_attached.has_value() && !*after.moveit_task_object_attached;
  const bool safe = retryable_code && physical_result.tcp_z_delta_m > 0.0 &&
                    physical_result.xy_slip_m <= PhysicalGraspThresholds{}.max_xy_slip_m &&
                    physical_result.orientation_change_rad <=
                      PhysicalGraspThresholds{}.max_orientation_change_rad &&
                    after.fresh && after.arm_stationary && after.gazebo_task_object_stationary &&
                    detached;
  if (!safe) {
    decision.rejection = rejection("PHYSICAL_GRASP_RETRY_NOT_SAFE",
                                   "Physical-grasp retry safety predicates are not satisfied");
    return decision;
  }

  decision.next.attempt_index = current.attempt_index + 1;
  if (!physical_result.gripper_contact)
    ++decision.next.contact_missing_count;
  const double deepest_allowed =
    std::max({profile.q6_contact - config.max_tighten_q6,
              profile.q6_contact - profile.q6_regrasp_squeeze_offset, profile.q6_safe_lower});
  const double requested =
    profile.q6_contact - static_cast<double>(decision.next.contact_missing_count) *
                           config.contact_missing_tighten_step_q6;
  decision.next.current_reclose_target_q6 = std::max(requested, deepest_allowed);
  decision.retry = true;
  return decision;
}
}  // namespace so101_gazebo_demo::pick_place
