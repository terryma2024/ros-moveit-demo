#include <cstdlib>
#include <exception>
#include <iostream>
#include <memory>
#include <string>

#include <rclcpp/rclcpp.hpp>

#include "so101_gazebo_demo/pick_place/gazebo_reset_adapter.hpp"
#include "so101_gazebo_demo/pick_place/moveit_scene_adapter.hpp"
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
  auto node = std::make_shared<rclcpp::Node>("reset_so101_world");
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto timeout_seconds = node->declare_parameter<double>("timeout_seconds", 3.0);
  const auto poll_interval_seconds = node->declare_parameter<double>("poll_interval_seconds", 0.05);
  const auto gazebo_observation_timeout_seconds =
    node->declare_parameter<double>("gazebo_observation_timeout_seconds", 0.5);
  const auto service_timeout_ms = node->declare_parameter<int>("service_timeout_ms", 1000);

  try {
    const pick_place::MoveItSceneGeometry geometry{profile.world_frame, profile.table_object,
                                                   profile.table_size,  profile.coke_model,
                                                   profile.coke_height, profile.coke_radius};
    auto moveit =
      std::make_shared<pick_place::MoveItSceneAdapter>(node, profile.planning_group, geometry);
    auto gazebo = std::make_shared<pick_place::GazeboResetAdapter>(
      profile.gazebo_world, profile.coke_model, profile.detach_topic,
      profile.attachment_state_topic, gazebo_observation_timeout_seconds,
      service_timeout_ms > 0 ? static_cast<unsigned int>(service_timeout_ms) : 0U);
    const pick_place::WorldResetConfig config{
      profile.table_pose, profile.coke_pose, timeout_seconds, poll_interval_seconds, 0.002, 0.02};
    pick_place::WorldResetCoordinator resetter(gazebo, moveit, config);
    const auto result = resetter.reset();
    if (result.status != pick_place::ActionStatus::SUCCEEDED) {
      const auto code = result.failure ? result.failure->code : "WORLD_RESET_FAILED";
      const auto message =
        result.failure ? result.failure->message : "SO-101 world reset failed without evidence";
      RCLCPP_ERROR(node->get_logger(), "%s: %s", code.c_str(), message.c_str());
      rclcpp::shutdown();
      return EXIT_FAILURE;
    }
  } catch (const std::exception & error) {
    RCLCPP_ERROR(node->get_logger(), "SO-101 world reset exception: %s", error.what());
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }

  RCLCPP_INFO(node->get_logger(),
              "Gazebo and MoveIt converged to detached canonical SO-101 world facts");
  rclcpp::shutdown();
  return EXIT_SUCCESS;
}
