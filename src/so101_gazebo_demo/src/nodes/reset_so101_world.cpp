#include <cstdlib>
#include <exception>
#include <filesystem>
#include <iostream>
#include <memory>
#include <string>

#include <ament_index_cpp/get_package_share_directory.hpp>
#include <rclcpp/rclcpp.hpp>

#include "so101_gazebo_demo/pick_place/gazebo_reset_adapter.hpp"
#include "so101_gazebo_demo/pick_place/follow_joint_trajectory_gripper_adapter.hpp"
#include "so101_gazebo_demo/pick_place/moveit_joint_planning_boundary.hpp"
#include "so101_gazebo_demo/pick_place/moveit_scene_adapter.hpp"
#include "so101_gazebo_demo/pick_place/node_spinner.hpp"
#include "so101_gazebo_demo/pick_place/policy_config.hpp"
#include "so101_gazebo_demo/pick_place/robot_home_reset_adapter.hpp"
#include "so101_gazebo_demo/pick_place/so101_profile.hpp"
#include "so101_gazebo_demo/pick_place/world_reset_coordinator.hpp"

namespace pick_place = so101_gazebo_demo::pick_place;

int main(int argc, char * argv[])
{
  if (argc == 2 && std::string(argv[1]) == "--help") {
    std::cout << "reset_so101_world [--ros-args ...]\n";
    return EXIT_SUCCESS;
  }

  rclcpp::init(argc, argv);
  rclcpp::NodeOptions node_options;
  node_options.parameter_overrides({rclcpp::Parameter("use_sim_time", true)});
  auto node = std::make_shared<rclcpp::Node>("reset_so101_world", node_options);
  pick_place::NodeSpinner spinner(node);
  const std::filesystem::path share =
    ament_index_cpp::get_package_share_directory("so101_gazebo_demo");
  const pick_place::PolicyPaths policy_paths{
    node->declare_parameter<std::string>(
      "object_config", (share / "config/task_objects/light_plastic_cup.yaml").string()),
    node->declare_parameter<std::string>(
      "motion_policy", (share / "config/motion_policies/light_cup_wall_pick.yaml").string()),
    node->declare_parameter<std::string>(
      "validation_policy",
      (share / "config/validation_policies/light_cup_wall_pick.yaml").string())};
  const auto loaded = pick_place::loadPolicyBundle(policy_paths);
  if (!loaded.bundle) {
    const auto failure =
      loaded.failure.value_or(pick_place::Failure{pick_place::FailureCategory::CONFIGURATION,
                                                  "POLICY_INVALID_VALUE",
                                                  "reset policy loading failed without evidence",
                                                  {}});
    RCLCPP_ERROR(node->get_logger(), "%s", pick_place::formatFailure(failure).c_str());
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }
  const auto profile = pick_place::SO101Profile::configured(
    loaded.bundle->object, loaded.bundle->motion, loaded.bundle->validation);
  const auto timeout_seconds = node->declare_parameter<double>("timeout_seconds", 10.0);
  const auto poll_interval_seconds = node->declare_parameter<double>("poll_interval_seconds", 0.05);
  const auto gazebo_observation_timeout_seconds =
    node->declare_parameter<double>("gazebo_observation_timeout_seconds", 0.5);
  const auto service_timeout_ms = node->declare_parameter<int>("service_timeout_ms", 1000);
  const auto joint_state_timeout_seconds =
    node->declare_parameter<double>("joint_state_timeout_seconds", 3.0);
  const auto arm_velocity_scaling = node->declare_parameter<double>("arm_velocity_scaling", 0.15);
  const auto arm_acceleration_scaling =
    node->declare_parameter<double>("arm_acceleration_scaling", 0.15);
  const auto gripper_trajectory_seconds =
    node->declare_parameter<double>("gripper_trajectory_seconds", 1.0);
  const auto gripper_action_timeout_seconds =
    node->declare_parameter<double>("gripper_action_timeout_seconds", 8.0);
  const auto arm_home_position_tolerance =
    node->declare_parameter<double>("arm_home_position_tolerance", 0.002);

  try {
    const pick_place::MoveItSceneGeometry geometry{profile.world_frame,
                                                   profile.table_object,
                                                   profile.table_size,
                                                   profile.pedestal_object,
                                                   profile.pedestal_size,
                                                   profile.task_object_id,
                                                   profile.task_object_height,
                                                   profile.task_object_outer_radius,
                                                   profile.task_object_wall_thickness,
                                                   profile.task_object_bottom_thickness,
                                                   profile.task_object_side_count};
    auto moveit =
      std::make_shared<pick_place::MoveItSceneAdapter>(node, profile.planning_group, geometry);
    auto gazebo = std::make_shared<pick_place::GazeboResetAdapter>(
      profile.gazebo_world, profile.task_object_id, profile.detach_topic,
      profile.attachment_state_topic, gazebo_observation_timeout_seconds,
      service_timeout_ms > 0 ? static_cast<unsigned int>(service_timeout_ms) : 0U);
    auto joints = std::make_shared<pick_place::MoveItJointPlanningBoundary>(
      node, profile, "RRTConnectkConfigDefault", arm_velocity_scaling, arm_acceleration_scaling,
      joint_state_timeout_seconds);
    auto arm = std::make_shared<pick_place::MoveGroupArmHomePlanningBoundary>(
      node, profile.planning_group, arm_home_position_tolerance, arm_velocity_scaling,
      arm_acceleration_scaling);
    auto gripper_client =
      std::make_shared<pick_place::RosTrajectoryActionClient>(node, profile.gripper_action);
    auto gripper = std::make_shared<pick_place::FollowJointTrajectoryGripperAdapter>(
      gripper_client, gripper_trajectory_seconds, gripper_action_timeout_seconds);
    auto robot =
      std::make_shared<pick_place::MoveItRobotHomeResetAdapter>(arm, joints, gripper, profile);
    pick_place::WorldResetConfig config{profile.table_pose,
                                        profile.pedestal_pose,
                                        profile.task_object_pose,
                                        profile.reset_parking_task_object_pose,
                                        timeout_seconds,
                                        poll_interval_seconds,
                                        0.002,
                                        0.02};
    config.arm_joints = profile.arm_joints;
    config.arm_home_positions = profile.arm_home_positions;
    config.gripper_joint = profile.gripper_joint;
    config.q6_release_position = profile.q6_full_open;
    config.q6_safe_lower = profile.q6_safe_lower;
    config.q6_home_position = profile.q6_safe_lower;
    config.arm_joint_position_tolerance = arm_home_position_tolerance;
    config.gripper_position_tolerance = profile.q6_tolerance;
    config.joint_velocity_tolerance = profile.q6_velocity_tolerance;
    pick_place::WorldResetCoordinator resetter(gazebo, moveit, robot, config);
    const auto result = resetter.reset();
    if (result.status != pick_place::ActionStatus::SUCCEEDED) {
      const auto message =
        result.failure ? pick_place::formatFailure(*result.failure)
                       : std::string("failure=WORLD_RESET_FAILED\n"
                                     "failure_message=SO-101 world reset failed without evidence");
      RCLCPP_ERROR(node->get_logger(), "%s", message.c_str());
      rclcpp::shutdown();
      return EXIT_FAILURE;
    }
  } catch (const std::exception & error) {
    RCLCPP_ERROR(node->get_logger(), "SO-101 world reset exception: %s", error.what());
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }

  RCLCPP_INFO(node->get_logger(),
              "Gazebo, MoveIt, arm, and gripper converged to canonical SO-101 reset facts");
  rclcpp::shutdown();
  return EXIT_SUCCESS;
}
