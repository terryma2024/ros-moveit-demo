#include <chrono>
#include <cstdlib>
#include <memory>
#include <string>
#include <thread>
#include <vector>
#include <cmath>

#include <geometry_msgs/msg/pose.hpp>
#include <moveit/move_group_interface/move_group_interface.hpp>
#include <moveit/planning_scene_interface/planning_scene_interface.hpp>
#include <moveit_msgs/msg/robot_trajectory.hpp>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp/executors/single_threaded_executor.hpp>

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);

  auto node = std::make_shared<rclcpp::Node>(
    "attach_and_lift_demo",
    rclcpp::NodeOptions().automatically_declare_parameters_from_overrides(true));

  auto executor = std::make_shared<rclcpp::executors::SingleThreadedExecutor>();

  executor->add_node(node);

  std::thread([executor]() { executor->spin(); }).detach();

  const auto logger = node->get_logger();

  const bool execute_lift = node->get_parameter_or("execute_lift", false);
  const double lift_distance = node->get_parameter_or("lift_distance", 0.03);
  const bool plan_lift = node->get_parameter_or("plan_lift", false);
  const bool detach_moveit = node->get_parameter_or("detach_moveit", false);

  if (std::abs(lift_distance) < 1e-6 || std::abs(lift_distance) > 0.10) {
    RCLCPP_ERROR(logger, "absolute lift_distance must be in [1e-6, 0.10]");
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }

  if (execute_lift && !plan_lift) {
    RCLCPP_ERROR(logger, "execute_lift requires plan_lift=true");
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }

  using MoveGroupInterface = moveit::planning_interface::MoveGroupInterface;
  MoveGroupInterface move_group(node, "panda_arm");
  move_group.setPoseReferenceFrame("world");
  move_group.setEndEffectorLink("panda_tcp");
  move_group.setMaxVelocityScalingFactor(0.05);
  move_group.setMaxAccelerationScalingFactor(0.05);

  if (!move_group.startStateMonitor(2.0)) {
    RCLCPP_ERROR(logger, "Failed to start current state monitor");
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }

  const std::vector<std::string> touch_links{"panda_hand", "panda_leftfinger", "panda_rightfinger"};

  moveit::planning_interface::PlanningSceneInterface planning_scene;

  if (detach_moveit) {
    if (!move_group.detachObject("coke")) {
      RCLCPP_ERROR(logger, "Failed to send MoveIt detach request for coke");
      rclcpp::shutdown();
      return EXIT_FAILURE;
    }

    bool detached = false;

    for (int attempt = 0; attempt < 20; ++attempt) {
      const bool no_longer_attached =
        planning_scene.getAttachedObjects({"coke"}).count("coke") == 0;

      const bool returned_to_world = planning_scene.getObjects({"coke"}).count("coke") == 1;

      if (no_longer_attached && returned_to_world) {
        detached = true;
        break;
      }

      std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    if (!detached) {
      RCLCPP_ERROR(logger, "coke did not transition from attached object to world object");
      rclcpp::shutdown();
      return EXIT_FAILURE;
    }

    RCLCPP_INFO(logger, "MoveIt detached coke and returned it to world");

    rclcpp::shutdown();
    return EXIT_SUCCESS;
  }

  if (!move_group.attachObject("coke", "panda_hand", touch_links)) {
    RCLCPP_ERROR(logger, "Failed to send MoveIt attach request for coke");
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }

  bool attached = false;
  for (int attempt = 0; attempt < 20; ++attempt) {
    if (planning_scene.getAttachedObjects({"coke"}).count("coke") == 1) {
      attached = true;
      break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  }

  if (!attached) {
    RCLCPP_ERROR(logger, "coke did not appear in MoveIt attached objects");
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }

  const bool still_in_world = planning_scene.getObjects({"coke"}).count("coke") == 1;
  if (still_in_world) {
    RCLCPP_ERROR(logger, "coke is both a world object and an attached object");
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }

  RCLCPP_INFO(logger,
              "MoveIt attached coke to panda_hand; touch links: panda_hand and both fingers");

  if (!plan_lift) {
    RCLCPP_INFO(logger, "Attach-only mode; pass plan_lift:=true for a 30 mm test lift");
    rclcpp::shutdown();
    return EXIT_SUCCESS;
  }

  move_group.setStartStateToCurrentState();
  geometry_msgs::msg::Pose lift_pose = move_group.getCurrentPose("panda_tcp").pose;
  lift_pose.position.z += lift_distance;

  std::vector<geometry_msgs::msg::Pose> waypoints{lift_pose};
  moveit_msgs::msg::RobotTrajectory trajectory;
  moveit_msgs::msg::MoveItErrorCodes error;
  const double fraction =
    move_group.computeCartesianPath(waypoints, 0.002, trajectory, true, &error);

  RCLCPP_INFO(logger, "Cartesian lift: %.1f%%, distance=%.3f m, points=%zu, error=%d",
              fraction * 100.0, lift_distance, trajectory.joint_trajectory.points.size(),
              error.val);

  if (fraction < 0.999 || trajectory.joint_trajectory.points.empty()) {
    RCLCPP_ERROR(logger, "Lift path is incomplete; refusing execution");
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }

  if (!execute_lift) {
    RCLCPP_INFO(logger, "Lift fully planned; not executing");
    rclcpp::shutdown();
    return EXIT_SUCCESS;
  }

  const bool executed = static_cast<bool>(move_group.execute(trajectory));
  if (!executed) {
    RCLCPP_ERROR(logger, "Lift execution failed");
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }

  RCLCPP_INFO(logger, "Lift execution succeeded");
  rclcpp::shutdown();
  return EXIT_SUCCESS;
}
