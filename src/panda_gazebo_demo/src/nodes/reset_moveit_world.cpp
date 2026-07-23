#include <cstdlib>
#include <exception>
#include <iostream>
#include <memory>
#include <string>

#include <rclcpp/rclcpp.hpp>

#include "panda_gazebo_demo/pick_place/moveit_scene_adapter.hpp"
#include "panda_gazebo_demo/pick_place/moveit_world_resetter.hpp"

namespace pick_place = panda_gazebo_demo::pick_place;

int main(int argc, char * argv[])
{
  if (argc == 2 && std::string(argv[1]) == "--help") {
    std::cout << "reset_moveit_world [--ros-args ...]\n";
    return EXIT_SUCCESS;
  }

  rclcpp::init(argc, argv);
  auto node = std::make_shared<rclcpp::Node>("reset_moveit_world");
  const auto planning_group = node->declare_parameter<std::string>("planning_group", "panda_arm");
  const auto object_id = node->declare_parameter<std::string>("object_id", "coke");
  const auto timeout_seconds = node->declare_parameter<double>("timeout_seconds", 2.0);
  const auto poll_interval_seconds = node->declare_parameter<double>("poll_interval_seconds", 0.05);

  if (planning_group.empty() || object_id.empty()) {
    RCLCPP_ERROR(node->get_logger(), "planning_group and object_id must not be empty");
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }

  try {
    auto adapter =
      std::make_shared<pick_place::MoveItSceneAdapter>(node, planning_group, object_id);
    pick_place::MoveItWorldResetter resetter(adapter, timeout_seconds, poll_interval_seconds);
    const pick_place::Pose3d target_pose{0.3, 0.0, 0.836, 0.0, 0.0, 0.0, 1.0};
    const auto result = resetter.reset(target_pose);
    if (result.status != pick_place::ActionStatus::SUCCEEDED) {
      const auto code = result.failure ? result.failure->code : "MOVEIT_RESET_FAILED";
      const auto message = result.failure ? result.failure->message
                                          : "MoveIt world reset failed without detailed evidence";
      RCLCPP_ERROR(node->get_logger(), "%s: %s", code.c_str(), message.c_str());
      rclcpp::shutdown();
      return EXIT_FAILURE;
    }
  } catch (const std::exception & error) {
    RCLCPP_ERROR(node->get_logger(), "MoveIt world reset exception: %s", error.what());
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }

  RCLCPP_INFO(node->get_logger(), "MoveIt Coke is detached at x=0.300000 y=0.000000 z=0.836000");
  rclcpp::shutdown();
  return EXIT_SUCCESS;
}
