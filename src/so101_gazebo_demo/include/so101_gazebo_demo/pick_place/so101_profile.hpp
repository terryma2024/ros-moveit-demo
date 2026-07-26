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
  double coke_radius{0.033};
  double coke_height{0.122};
  Pose3d coke_pose{0.02, -0.28, 0.181, 0.0, 0.0, 0.0, 1.0};
  double q6_preopen{0.707194871};
  double q6_contact{0.662818811};
  double q6_full_open{1.7};
  double preopen_width{0.070};
  double contact_width{0.066};
  double grasp_section_depth{0.020};
  std::string gripper_geometry_model_version{"so101-gripper-d20-mesh-v1"};
  std::string gripper_geometry_model_fingerprint{
    "33be401ad080298b31265a7ab60f4e233da4d3abd6aafb090f6a4fce7bed2a4e"};
  double q6_tolerance{0.002};
  double width_tolerance{0.0005};
  double q6_velocity_tolerance{0.01};
  double coke_position_drift_tolerance{0.003};
  double coke_orientation_drift_tolerance_rad{0.035};
  std::string attach_topic{"/so101/attach_coke"};
  std::string detach_topic{"/so101/detach_coke"};
  std::string attachment_event_topic{"/so101/coke_attached_event"};
  std::string attachment_state_topic{"/so101/coke_attached"};

  [[nodiscard]] static const SO101Profile & canonical() noexcept;
};

}  // namespace so101_gazebo_demo::pick_place
