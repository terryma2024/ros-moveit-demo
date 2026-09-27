#include <gtest/gtest.h>
#include <pluginlib/class_loader.hpp>
#include <rclcpp/rclcpp.hpp>

#include "so101_mujoco_support/broker_owned_trajectory_controller.hpp"

namespace
{
class InspectableController : public so101_mujoco_support::BrokerOwnedTrajectoryController
{
public:
  bool topic_subscriber_exists() const {return static_cast<bool>(joint_command_subscriber_);}
  bool action_server_exists() const {return static_cast<bool>(action_server_);}
};
}

TEST(BrokerOwnedTrajectoryController, ConfigureHasNoTopicCommandIngress)
{
  rclcpp::init(0, nullptr);
  InspectableController controller;
  rclcpp::NodeOptions options;
  options.parameter_overrides({
    rclcpp::Parameter("joints", std::vector<std::string>{"1", "2", "3", "4", "5"}),
    rclcpp::Parameter("command_interfaces", std::vector<std::string>{"position"}),
    rclcpp::Parameter("state_interfaces", std::vector<std::string>{"position", "velocity"}),
  });
  ASSERT_EQ(controller.init("arm_controller", "", 500, "", options),
    controller_interface::return_type::OK);
  ASSERT_EQ(controller.configure().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  EXPECT_FALSE(controller.topic_subscriber_exists());
  EXPECT_EQ(controller.get_node()->count_subscribers("/arm_controller/joint_trajectory"), 0U);
  EXPECT_TRUE(controller.action_server_exists());
  rclcpp::shutdown();
}

TEST(BrokerOwnedTrajectoryController, RegisteredForControllerManager)
{
  pluginlib::ClassLoader<controller_interface::ControllerInterface> loader(
    "controller_interface", "controller_interface::ControllerInterface");
  ASSERT_TRUE(loader.isClassAvailable("so101_mujoco_support/BrokerOwnedTrajectoryController"));
  EXPECT_NE(loader.createSharedInstance(
    "so101_mujoco_support/BrokerOwnedTrajectoryController"), nullptr);
}
