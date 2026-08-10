#include "so101_gazebo_demo/pick_place/physical_grasp_validator.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

namespace so101_gazebo_demo::pick_place
{
namespace
{
Failure failure(std::string code, std::string message, const PhysicalGraspResult & result)
{
  return {FailureCategory::POSTCONDITION,
          std::move(code),
          std::move(message),
          {{"table_clearance_m", result.table_clearance_m},
           {"cup_bottom_z_m", result.cup_bottom_z_m},
           {"tcp_z_delta_m", result.tcp_z_delta_m},
           {"cup_z_delta_m", result.cup_z_delta_m},
           {"cup_follow_ratio", result.cup_follow_ratio},
           {"xy_slip_m", result.xy_slip_m},
           {"orientation_change_rad", result.orientation_change_rad},
           {"position_error_m", result.position_error_m},
           {"gripper_contact", result.gripper_contact ? 1.0 : 0.0}}};
}
}  // namespace

PhysicalGraspValidator::PhysicalGraspValidator(PhysicalGraspThresholds thresholds) :
    thresholds_(thresholds)
{
}

PhysicalGraspResult PhysicalGraspValidator::evaluate(const WorldSnapshot & before,
                                                     const WorldSnapshot & after,
                                                     const PhysicalGraspGeometry & geometry) const
{
  PhysicalGraspResult result;
  if (!before.gazebo_task_object_pose_world || !after.gazebo_task_object_pose_world ||
      !before.fresh || !after.fresh) {
    result.failure =
      failure("PHYSICAL_GRASP_EVIDENCE_STALE", "Fresh cup pose evidence is required", result);
    return result;
  }
  const auto & cup_before = *before.gazebo_task_object_pose_world;
  const auto & cup_after = *after.gazebo_task_object_pose_world;
  result.cup_bottom_z_m = cup_after.z + geometry.cup_bottom_offset_z_m;
  result.table_clearance_m = result.cup_bottom_z_m - geometry.table_surface_z_m;
  result.tcp_z_delta_m = after.tcp_pose_world.z - before.tcp_pose_world.z;
  result.cup_z_delta_m = cup_after.z - cup_before.z;
  result.cup_follow_ratio =
    std::abs(result.tcp_z_delta_m) <= 1e-12 ? 0.0 : result.cup_z_delta_m / result.tcp_z_delta_m;
  result.xy_slip_m = std::hypot(cup_after.x - cup_before.x, cup_after.y - cup_before.y);
  const double z_tracking_error = result.cup_z_delta_m - result.tcp_z_delta_m;
  result.position_error_m = std::hypot(result.xy_slip_m, z_tracking_error);
  result.orientation_change_rad = orientationDistance(cup_before, cup_after);
  result.gripper_contact = after.gazebo_task_object_gripper_contact.value_or(false);
  if (thresholds_.require_arm_stable && (!before.arm_stationary || !after.arm_stationary)) {
    result.failure =
      failure("PHYSICAL_GRASP_ARM_UNSTABLE", "Arm must be stable around the micro lift", result);
  } else if (result.cup_z_delta_m < thresholds_.minimum_axial_progress_m) {
    result.failure = failure("PHYSICAL_GRASP_INSUFFICIENT_LIFT",
                             "Cup did not make the minimum upward progress", result);
  } else if (result.xy_slip_m > thresholds_.max_xy_slip_m) {
    result.failure = failure("PHYSICAL_GRASP_XY_SLIP", "Cup XY slip exceeds threshold", result);
  } else if (result.position_error_m > thresholds_.maximum_position_error_m) {
    result.failure = failure("PHYSICAL_GRASP_POSITION_ERROR",
                             "Cup did not follow the commanded micro-lift displacement", result);
  } else if (thresholds_.require_gripper_contact && !result.gripper_contact) {
    result.failure =
      failure("PHYSICAL_GRASP_CONTACT_MISSING", "Cup/gripper contact is required", result);
  } else if (result.table_clearance_m <= thresholds_.min_table_clearance_m) {
    result.failure =
      failure("PHYSICAL_GRASP_TABLE_CLEARANCE", "Cup did not clear the table", result);
  } else if (result.cup_follow_ratio < thresholds_.min_cup_follow_ratio) {
    result.failure =
      failure("PHYSICAL_GRASP_FOLLOW_RATIO", "Cup did not follow the micro lift", result);
  } else if (result.orientation_change_rad > thresholds_.max_orientation_change_rad) {
    result.failure =
      failure("PHYSICAL_GRASP_ORIENTATION", "Cup orientation changed too far", result);
  } else {
    result.passed = true;
  }
  return result;
}
}  // namespace so101_gazebo_demo::pick_place
