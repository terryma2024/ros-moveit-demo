#pragma once

#include <array>
#include <string>
#include <vector>

#include "so101_gazebo_demo/pick_place/fingertip_pad_gap_calibration_data.hpp"
#include "so101_gazebo_demo/pick_place/policy_config.hpp"
#include "so101_gazebo_demo/pick_place/world_observer.hpp"

namespace so101_gazebo_demo::pick_place
{

struct SO101Profile
{
  std::string world_frame{"world"};
  std::string gazebo_world{"so101_pick_place"};
  std::string planning_group{"arm"};
  std::string tcp_link{"so101_tcp"};
  std::vector<std::string> arm_joints{"1", "2", "3", "4", "5"};
  std::string gripper_joint{"6"};
  std::string gripper_action{"/gripper_controller/follow_joint_trajectory"};
  std::string arm_action{"/arm_controller/follow_joint_trajectory"};
  std::string moveit_attach_link{"gripper"};
  std::vector<std::string> moveit_touch_links{"gripper", "jaw"};
  std::string task_object_id{"plastic_cup"};
  std::string task_object_link{"body"};
  std::string table_object{"table"};
  std::array<double, 3> table_size{0.50, 0.60, 0.04};
  Pose3d table_pose{0.0, -0.20, 0.10, 0.0, 0.0, 0.0, 1.0};
  std::string pedestal_object{"base_pedestal"};
  std::array<double, 3> pedestal_size{0.18, 0.18, 0.10};
  Pose3d pedestal_pose{0.0, 0.0, 0.17, 0.0, 0.0, 0.0, 1.0};
  double task_object_outer_radius{0.040};
  double task_object_height{0.090};
  double task_object_wall_thickness{0.002};
  double task_object_bottom_thickness{0.002};
  int task_object_side_count{12};
  Vec3 task_object_near_wall_outward{0.0, 1.0, 0.0};
  Pose3d task_object_pose{0.02, -0.28, 0.165, 0.0, 0.0, 0.0, 1.0};
  Pose3d place_task_object_pose{-0.08, -0.25, 0.165, 0.0, 0.0, 0.0, 1.0};
  Pose3d calibrated_grasp_relative_pose{
    0.026397024348, 0.000172476372, -0.153948999996,
    -0.000000367000, 0.000000354000, 0.719203129000, 0.694799870000};
  std::vector<double> arm_home_positions{0.0, 0.0, 0.0, 0.0, 0.0};
  double q6_safe_lower{-0.059303612618397};
  double q6_home{-0.059303612618397};
  double q6_preopen{0.465038};
  double q6_geometric_side_contact{0.662818811};
  // Command the calibrated Bullet contact stop instead of locking penetration
  // into the DetachableJoint constraint.
  double q6_close{fingertip_pad_calibration::kGraspQ6};
  double q6_contact{fingertip_pad_calibration::kGraspQ6};
  double q6_full_open{1.7};
  double preopen_width{0.039453338646308};
  double contact_width{fingertip_pad_calibration::kGraspGapM};
  std::string fingertip_pad_calibration_fingerprint{
    "b101b7db33a13c82797eb80c2356f1c6b509e04bdae7999efd4b6a8ce0d1094f"};
  double grasp_section_depth{0.020};
  std::string gripper_geometry_model_version{"so101-gripper-d20-mesh-v1"};
  std::string gripper_geometry_model_fingerprint{
    "8d541b21f53327500776c611227323c30e8dceb69844535235c46704836cc127"};
  // Preopen and native-pad grasp use the configured position tolerance.  The
  // release endpoint gets a separate settling allowance below.
  double q6_tolerance{0.001};
  double q6_full_open_tolerance{0.010};
  double width_tolerance{0.0005};
  double contact_q6_stop_tolerance{0.010};
  double contact_width_oversize_tolerance{0.001};
  double max_gripper_contact_depth{0.002};
  double grasp_contact_min_height_above_center{0.015};
  double grasp_contact_top_edge_clearance{0.006};
  double q6_velocity_tolerance{0.01};
  double task_object_position_drift_tolerance{0.003};
  double task_object_orientation_drift_tolerance_rad{0.035};
  double post_attach_hold_settle_seconds{2.0};
  std::string attach_topic{"/so101/attach_object"};
  std::string detach_topic{"/so101/detach_object"};
  std::string attachment_event_topic{"/so101/object_attached_event"};
  std::string attachment_state_topic{"/so101/object_attached"};

  [[nodiscard]] static const SO101Profile & canonical() noexcept;
  [[nodiscard]] static SO101Profile configured(
    const TaskObjectConfig & object,
    const MotionPolicyConfig & motion,
    const ValidationPolicyConfig & validation);
};

}  // namespace so101_gazebo_demo::pick_place
