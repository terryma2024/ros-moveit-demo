#pragma once

#include <array>
#include <string>
#include <vector>

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
  std::string coke_model{"coke"};
  std::string coke_link{"body"};
  std::string table_object{"table"};
  std::array<double, 3> table_size{0.50, 0.60, 0.04};
  Pose3d table_pose{0.0, -0.20, 0.10, 0.0, 0.0, 0.0, 1.0};
  std::string pedestal_object{"base_pedestal"};
  std::array<double, 3> pedestal_size{0.18, 0.18, 0.10};
  Pose3d pedestal_pose{0.0, 0.0, 0.17, 0.0, 0.0, 0.0, 1.0};
  double coke_radius{0.033};
  double coke_height{0.122};
  Pose3d coke_pose{0.02, -0.28, 0.181, 0.0, 0.0, 0.0, 1.0};
  Pose3d place_coke_pose{-0.08, -0.25, 0.181, 0.0, 0.0, 0.0, 1.0};
  Pose3d calibrated_grasp_relative_pose{
    0.0214000012, -0.0000000417348703, -0.109949,
    -0.000000366, 0.000000355, 0.717401384, 0.696660071};
  std::vector<double> arm_home_positions{0.0, 0.0, 0.0, 0.0, 0.0};
  double q6_home{0.0};
  double q6_preopen{1.100000000};
  // The real STL section reaches a 66 mm side aperture at this angle.  With the
  // VHACD collision pieces, Coke first contacts the upper jaw feature earlier;
  // keep the two values separate so the position controller does not continue
  // driving through that authoritative Bullet contact while carrying.
  double q6_geometric_side_contact{0.790272757};
  double q6_close{1.030000000};
  double q6_contact{1.067000000};
  double q6_full_open{1.7};
  double preopen_width{0.094176917906};
  double contact_width{0.088951652};
  double grasp_section_depth{0.035};
  std::string gripper_geometry_model_version{"so101-gripper-d35-mesh-v1"};
  std::string gripper_geometry_model_fingerprint{
    "cb3ea447c0ec8e0e7dc2a70ef80f06244dde8004bd16fac36db531748cf29cb9"};
  // Bullet Featherstone settles about 0.010 rad above preopen and up to about
  // 0.015 rad above the VHACD contact-hold target.  This tolerance is still an
  // order of magnitude below the former 0.25 rad forced-penetration error;
  // width, contact and stop-velocity checks remain independent gates.
  double q6_tolerance{0.020};
  double width_tolerance{0.0005};
  double contact_q6_stop_tolerance{0.010};
  double contact_width_oversize_tolerance{0.001};
  double q6_velocity_tolerance{0.01};
  double coke_position_drift_tolerance{0.003};
  double coke_orientation_drift_tolerance_rad{0.035};
  double post_attach_hold_settle_seconds{2.0};
  std::string attach_topic{"/so101/attach_coke"};
  std::string detach_topic{"/so101/detach_coke"};
  std::string attachment_event_topic{"/so101/coke_attached_event"};
  std::string attachment_state_topic{"/so101/coke_attached"};

  [[nodiscard]] static const SO101Profile & canonical() noexcept;
};

}  // namespace so101_gazebo_demo::pick_place
