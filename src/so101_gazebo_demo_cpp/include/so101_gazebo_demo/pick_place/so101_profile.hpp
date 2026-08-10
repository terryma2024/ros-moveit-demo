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
  Pose3d reset_parking_task_object_pose{0.19, -0.44, 0.165, 0.0, 0.0, 0.0, 1.0};
  Pose3d calibrated_grasp_relative_pose{0.026397024348,  0.000172476372, -0.153948999996,
                                        -0.000000367000, 0.000000354000, 0.719203129000,
                                        0.694799870000};
  std::vector<double> arm_home_positions{0.0, 0.0, 0.0, 0.0, 0.0};
  double q6_safe_lower{-0.059600220867817};
  double q6_home{-0.059600220867817};
  double q6_preopen{0.465038};
  double q6_geometric_side_contact{0.662818811};
  // Command the calibrated Bullet contact stop instead of locking penetration
  // into the DetachableJoint constraint.
  double q6_close{fingertip_pad_calibration::kGraspQ6};
  double q6_contact{fingertip_pad_calibration::kGraspQ6};
  // One bounded retry adds about 0.49 mm of mesh-calibrated wall interference.
  // Keep more than 5 mrad of travel above the generated safe lower limit; the
  // Bullet compound-link friction fix supplies lift capacity without crushing
  // the 2 mm cup wall toward the 1 mm safe-floor gap.
  double q6_regrasp_squeeze_offset{0.0060};
  double q6_full_open{1.7};
  std::vector<double> release_stages_q6;
  double preopen_width{fingertip_pad_calibration::kPreopenGapM};
  double contact_width{fingertip_pad_calibration::kGraspGapM};
  std::string fingertip_pad_calibration_fingerprint{
    "b2366fcc60cd2c08611f2bd4a17850eba0be13f002e2bde3b431e9866062d320"};
  double grasp_section_depth{0.020};
  std::string gripper_geometry_model_version{"so101-gripper-d20-mesh-v1"};
  std::string gripper_geometry_model_fingerprint{
    "7c848527a6b93c916d82b5e2902b9eed9ce457333c249d30cb2757815c22f247"};
  // Preopen and native-pad grasp use the configured position tolerance.  The
  // release endpoint gets a separate settling allowance below.
  double q6_tolerance{0.001};
  double q6_full_open_tolerance{0.012};
  double width_tolerance{0.0005};
  double contact_q6_stop_tolerance{0.010};
  double contact_width_oversize_tolerance{0.001};
  double max_gripper_contact_depth{0.002};
  double max_dynamic_wall_interference{0.00010};
  double grasp_contact_min_height_above_center{0.015};
  double grasp_contact_top_edge_clearance{0.006};
  double q6_velocity_tolerance{0.01};
  // Preserve a 5 mm bound for physical cup motion while bilateral pad contact
  // remains intact; contact depth and final support pose are checked separately.
  double task_object_position_drift_tolerance{0.005};
  // Release support is evaluated while the MoveIt collision-planning shadow
  // remains attached. The physical cup can sit slightly high and can freely
  // yaw because its body is rotationally symmetric.
  double place_support_xy_tolerance{0.005};
  double place_detach_xy_tolerance{0.006};
  double place_pre_detach_height_tolerance{0.012};
  double place_support_height_tolerance{0.010};
  double place_support_tilt_tolerance_rad{0.08726646259971647};
  // Keep a bounded 0.070 rad tilt envelope (4.01 deg) for physical carry
  // validation; axial self-spin is ignored because the TaskObject is cylindrical.
  double task_object_orientation_drift_tolerance_rad{0.070};
  // Bound absolute planning-shadow calibration tilt separately so accumulated
  // physical drift is not mistaken for a lost grasp.
  double task_object_attachment_orientation_tolerance_rad{0.08726646259971647};
  double post_attach_hold_settle_seconds{2.0};
  std::string attach_topic{"/so101/attach_object"};
  std::string detach_topic{"/so101/detach_object"};
  std::string attachment_event_topic{"/so101/object_attached_event"};
  std::string attachment_state_topic{"/so101/object_attached"};

  [[nodiscard]] static const SO101Profile & canonical() noexcept;
  [[nodiscard]] static SO101Profile configured(const TaskObjectConfig & object,
                                               const MotionPolicyConfig & motion,
                                               const ValidationPolicyConfig & validation);
};

}  // namespace so101_gazebo_demo::pick_place
