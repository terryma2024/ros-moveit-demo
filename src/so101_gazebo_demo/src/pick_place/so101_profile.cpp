#include "so101_gazebo_demo/pick_place/so101_profile.hpp"

#include <cmath>
#include <stdexcept>

#include "so101_gazebo_demo/pick_place/so101_gripper_validation.hpp"
#include "so101_gazebo_demo/pick_place/fingertip_pad_gap_calibration_data.hpp"

namespace so101_gazebo_demo::pick_place
{

const SO101Profile & SO101Profile::canonical() noexcept
{
  static const SO101Profile profile;
  return profile;
}

SO101Profile SO101Profile::configured(
  const TaskObjectConfig & object,
  const MotionPolicyConfig & motion,
  const ValidationPolicyConfig & validation)
{
  auto profile = canonical();
  profile.task_object_id = object.object_id;
  profile.task_object_height = object.model.height_m;
  profile.task_object_outer_radius = object.model.outer_radius_m;
  profile.task_object_wall_thickness = object.model.wall_thickness_m;
  profile.task_object_bottom_thickness = object.model.bottom_thickness_m;
  profile.task_object_side_count = object.model.side_count;
  profile.task_object_near_wall_outward = object.grasp_frame.near_wall_outward_world;
  profile.task_object_pose = object.scene.spawn_pose;
  profile.place_task_object_pose = object.scene.place_pose;
  profile.calibrated_grasp_relative_pose = object.grasp_frame.attachment_relative_pose;
  profile.q6_safe_lower = object.fingertip_pads.safe_lower_q6;
  profile.q6_home = profile.q6_safe_lower;
  profile.q6_preopen = motion.gripper_actions.preopen_q6;
  profile.q6_close = motion.gripper_actions.grasp_close_q6;
  profile.q6_contact = motion.gripper_actions.grasp_close_q6;
  profile.q6_full_open = motion.gripper_actions.release_q6;
  profile.release_stages_q6 = {0.209, 0.506, profile.q6_full_open};
  profile.q6_geometric_side_contact = object.fingertip_pads.geometry_reference_q6;
  profile.q6_tolerance = validation.runtime.q6_position_tolerance_rad;
  profile.contact_q6_stop_tolerance =
    validation.runtime.q6_contact_stop_tolerance_rad;
  profile.q6_velocity_tolerance = validation.runtime.q6_velocity_tolerance_rad_s;
  profile.max_gripper_contact_depth = validation.grasp_contact.max_penetration_m;
  profile.fingertip_pad_calibration_fingerprint = object.fingertip_pads.calibration_fingerprint;
  namespace pad_calibration = fingertip_pad_calibration;
  if (std::abs(profile.q6_safe_lower - pad_calibration::kSafeFloorQ6) > 1e-12 ||
      std::abs(profile.q6_contact - pad_calibration::kGraspQ6) > 1e-12 ||
      std::abs(profile.q6_preopen - pad_calibration::kPreopenQ6) > 1e-12 ||
      std::abs(object.fingertip_pads.grasp_gap_m - pad_calibration::kGraspGapM) > 1e-12 ||
      profile.fingertip_pad_calibration_fingerprint != pad_calibration::kInputFingerprint) {
    throw std::invalid_argument(
            "configured fingertip-pad q6 commands do not match the fingerprint-bound calibration");
  }
  profile.preopen_width = pad_calibration::kPreopenGapM;
  profile.contact_width = pad_calibration::kGraspGapM;
  if (!std::isfinite(profile.preopen_width) || !std::isfinite(profile.contact_width)) {
    throw std::invalid_argument(
            "configured q6 values are outside the mesh-derived width calibration");
  }
  return profile;
}

}  // namespace so101_gazebo_demo::pick_place
