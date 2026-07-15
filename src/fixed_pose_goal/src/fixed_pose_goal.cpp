#include <chrono>
#include <memory>
#include <thread>

#include <geometry_msgs/msg/pose_stamped.hpp>
#include <moveit/move_group_interface/move_group_interface.hpp>
#include <rclcpp/rclcpp.hpp>
#include <visualization_msgs/msg/interactive_marker_feedback.hpp>

namespace
{
constexpr char kFeedbackTopic[] =
  "/rviz_moveit_motion_planning_display/robot_interaction_interactive_marker_topic/feedback";
constexpr char kGoalMarkerName[] = "EE:goal_panda_link8";

void updateRvizQueryGoalState(
  const rclcpp::Node::SharedPtr & node,
  const geometry_msgs::msg::PoseStamped & target_pose)
{
  using Feedback = visualization_msgs::msg::InteractiveMarkerFeedback;
  auto publisher = node->create_publisher<Feedback>(kFeedbackTopic, rclcpp::QoS(10));

  constexpr auto discovery_timeout = std::chrono::seconds(2);
  const auto deadline = std::chrono::steady_clock::now() + discovery_timeout;
  while (rclcpp::ok() && publisher->get_subscription_count() == 0 &&
    std::chrono::steady_clock::now() < deadline)
  {
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
  }

  if (publisher->get_subscription_count() == 0) {
    RCLCPP_WARN(
      node->get_logger(),
      "No RViz subscriber found on %s; Query Goal State was not updated",
      kFeedbackTopic);
    return;
  }

  Feedback feedback;
  feedback.header = target_pose.header;
  feedback.client_id = node->get_fully_qualified_name();
  feedback.marker_name = kGoalMarkerName;
  feedback.control_name = "move";
  feedback.event_type = Feedback::POSE_UPDATE;
  feedback.pose = target_pose.pose;

  publisher->publish(feedback);
  RCLCPP_INFO(
    node->get_logger(), "Updated RViz Query Goal State via marker '%s'", kGoalMarkerName);

  // Keep the publisher alive briefly so DDS can deliver the feedback.
  std::this_thread::sleep_for(std::chrono::milliseconds(100));
}
}  // namespace

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);

  auto node = std::make_shared<rclcpp::Node>(
    "fixed_pose_goal",
    rclcpp::NodeOptions().automatically_declare_parameters_from_overrides(true));

  auto logger = node->get_logger();

  using moveit::planning_interface::MoveGroupInterface;
  auto move_group = MoveGroupInterface(node, "panda_arm");

  move_group.setPlanningTime(5.0);
  move_group.setMaxVelocityScalingFactor(0.1);
  move_group.setMaxAccelerationScalingFactor(0.1);
  move_group.setStartStateToCurrentState();

  geometry_msgs::msg::PoseStamped target_pose;
  target_pose.header.frame_id = "world";
  target_pose.header.stamp = node->now();

  target_pose.pose.position.x = 0.770;
  target_pose.pose.position.y = 0.165;
  target_pose.pose.position.z = 0.472;

  target_pose.pose.orientation.x = 0.466;
  target_pose.pose.orientation.y = -0.379;
  target_pose.pose.orientation.z = 0.798;
  target_pose.pose.orientation.w = 0.053;

  // These pose values describe panda_link8. Keep MoveIt and RViz Query Goal State in sync.
  move_group.setPoseTarget(target_pose, "panda_link8");
  updateRvizQueryGoalState(node, target_pose);

  MoveGroupInterface::Plan plan;
  const bool planned = static_cast<bool>(move_group.plan(plan));

  if (!planned) {
    RCLCPP_ERROR(logger, "Planning failed");
    rclcpp::shutdown();
    return 1;
  }

  RCLCPP_INFO(logger, "Planning succeeded; executing trajectory");

  const bool executed = static_cast<bool>(move_group.execute(plan));

  if (!executed) {
    RCLCPP_ERROR(logger, "Execution failed");
    rclcpp::shutdown();
    return 1;
  }

  RCLCPP_INFO(logger, "Execution succeeded");

  rclcpp::shutdown();
  return 0;
}
