#include <functional>
#include <memory>

#include <rclcpp/rclcpp.hpp>
#include <visualization_msgs/msg/interactive_marker_feedback.hpp>

namespace
{
constexpr char kFeedbackTopic[] =
  "/rviz_moveit_motion_planning_display/robot_interaction_interactive_marker_topic/feedback";
}

class InteractiveMarkerPoseFeedbackNode : public rclcpp::Node
{
public:
  InteractiveMarkerPoseFeedbackNode()
  : Node("interactive_marker_pose_feedback")
  {
    subscription_ = create_subscription<visualization_msgs::msg::InteractiveMarkerFeedback>(
      kFeedbackTopic,
      rclcpp::QoS(10),
      std::bind(
        &InteractiveMarkerPoseFeedbackNode::feedback_callback, this,
        std::placeholders::_1));

    RCLCPP_INFO(get_logger(), "Listening for target pose changes on %s", kFeedbackTopic);
  }

private:
  void feedback_callback(
    const visualization_msgs::msg::InteractiveMarkerFeedback::SharedPtr message) const
  {
    using Feedback = visualization_msgs::msg::InteractiveMarkerFeedback;
    if (message->event_type != Feedback::POSE_UPDATE) {
      return;
    }

    const auto & position = message->pose.position;
    const auto & orientation = message->pose.orientation;

    RCLCPP_INFO(
      get_logger(),
      "Target pose changed [marker='%s', control='%s', frame='%s']\n"
      "  position:    x=%.6f, y=%.6f, z=%.6f\n"
      "  orientation: x=%.6f, y=%.6f, z=%.6f, w=%.6f",
      message->marker_name.c_str(),
      message->control_name.c_str(),
      message->header.frame_id.c_str(),
      position.x, position.y, position.z,
      orientation.x, orientation.y, orientation.z, orientation.w);
  }

  rclcpp::Subscription<visualization_msgs::msg::InteractiveMarkerFeedback>::SharedPtr subscription_;
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<InteractiveMarkerPoseFeedbackNode>());
  rclcpp::shutdown();
  return 0;
}
