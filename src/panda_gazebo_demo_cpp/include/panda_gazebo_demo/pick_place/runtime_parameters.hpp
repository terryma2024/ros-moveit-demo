#pragma once

#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include "panda_gazebo_demo/pick_place/domain_types.hpp"

namespace panda_gazebo_demo::pick_place
{

struct PickPlaceParameters
{
  std::string planning_group{"panda_arm"};
  std::string tcp_link{"panda_tcp"};
  std::vector<std::string> required_world_objects{"table", "coke"};
  double velocity_scaling{0.10};
  double acceleration_scaling{0.10};
  double cartesian_eef_step{0.005};
  double cartesian_min_fraction{0.99};
  double joint_jump_threshold{0.20};
  double motion_start_joint_tolerance{0.010};
  std::string ready_named_target{"ready"};
  double ready_joint_tolerance{0.010};
  double tcp_position_tolerance{0.020};
  double tcp_orientation_tolerance_rad{0.0872665};
  double coke_position_tolerance{0.010};
  double coke_orientation_tolerance_rad{0.0872665};
  double gripper_open_position{0.040};
  double gripper_open_min_position{0.038};
  double gripper_close_position{0.000};
  double gripper_close_tolerance{0.004};
  double gripper_grasp_min_position{0.028};
  double gripper_grasp_max_position{0.037};
  double gripper_symmetry_tolerance{0.003};
  double joint_velocity_tolerance{0.010};
  double gripper_max_effort{0.0};
  double gripper_action_timeout_seconds{5.0};
  double attachment_timeout_seconds{2.0};
  double planning_scene_timeout_seconds{2.0};
  double state_poll_interval_seconds{0.05};
  double gazebo_initial_observation_timeout_seconds{30.0};
  double gazebo_observation_max_age_seconds{0.5};
  std::size_t coke_settle_samples{5};
  double coke_settle_interval_seconds{0.05};
  double coke_settle_position_tolerance{0.002};
  double coke_settle_orientation_tolerance_rad{0.020};
  double recovery_safe_height{0.987};
  std::string gazebo_world_name{"pick_place_world"};
  std::string gazebo_coke_model{"coke"};
  std::string gazebo_attach_topic{"/panda/attach_coke"};
  std::string gazebo_detach_topic{"/panda/detach_coke"};
  std::string gazebo_attachment_event_topic{"/panda/coke_attached_event"};
  std::string gazebo_attachment_topic{"/panda/coke_attached"};
  bool gazebo_coke_initially_detached{true};
  std::string gripper_action_name{"/panda_hand_controller/gripper_cmd"};
  std::uint64_t max_state_transitions{100};
};

[[nodiscard]] std::optional<Failure>
validatePickPlaceParameters(const PickPlaceParameters & parameters);
[[nodiscard]] std::string pickPlaceConfigurationHash(const PickPlaceParameters & parameters,
                                                     const std::string & target_policy_signature);

}  // namespace panda_gazebo_demo::pick_place
