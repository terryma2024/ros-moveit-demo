#include <gtest/gtest.h>

#include <atomic>
#include <chrono>
#include <memory>
#include <string>
#include <thread>

#include <control_msgs/action/gripper_command.hpp>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>

#include "panda_gazebo_demo/pick_place/gripper_command_adapter.hpp"

namespace panda_gazebo_demo::pick_place
{
namespace
{

using namespace std::chrono_literals;
using GripperCommand = control_msgs::action::GripperCommand;
using GoalHandle = rclcpp_action::ServerGoalHandle<GripperCommand>;

class RosContextTest : public ::testing::Test
{
protected:
  static void SetUpTestSuite()
  {
    rclcpp::init(0, nullptr);
  }

  static void TearDownTestSuite()
  {
    rclcpp::shutdown();
  }
};

TEST_F(RosContextTest, DelayedAcceptedGoalIsCancelledAfterCommandResponseTimeout)
{
  const auto suffix = std::to_string(std::chrono::steady_clock::now().time_since_epoch().count());
  const auto action_name = "/test_gripper_delayed_" + suffix;
  auto server_node = std::make_shared<rclcpp::Node>("gripper_server_" + suffix);
  auto client_node = std::make_shared<rclcpp::Node>("gripper_client_" + suffix);
  std::atomic_bool cancel_seen{false};
  std::shared_ptr<GoalHandle> accepted_goal;
  auto server = rclcpp_action::create_server<GripperCommand>(
    server_node, action_name,
    [](const rclcpp_action::GoalUUID &, const std::shared_ptr<const GripperCommand::Goal> &) {
      std::this_thread::sleep_for(120ms);
      return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
    },
    [&cancel_seen](const std::shared_ptr<GoalHandle> &) {
      cancel_seen = true;
      return rclcpp_action::CancelResponse::ACCEPT;
    },
    [&accepted_goal](const std::shared_ptr<GoalHandle> & goal_handle) {
      accepted_goal = goal_handle;
    });
  rclcpp::executors::MultiThreadedExecutor executor;
  executor.add_node(server_node);
  executor.add_node(client_node);
  std::thread spin_thread([&executor]() { executor.spin(); });
  GripperCommandAdapter adapter(client_node, action_name, 0.1);

  const auto command_result = adapter.command(0.04, 0.0);
  const auto cancel_result = adapter.cancelAndWait();

  executor.cancel();
  spin_thread.join();
  EXPECT_EQ(command_result.status, ActionStatus::TIMED_OUT);
  ASSERT_EQ(cancel_result.status, ActionStatus::SUCCEEDED)
    << (cancel_result.failure ? cancel_result.failure->code : "no failure");
  EXPECT_TRUE(cancel_seen.load());
  static_cast<void>(accepted_goal);
  static_cast<void>(server);
}

}  // namespace
}  // namespace panda_gazebo_demo::pick_place
