#include <gtest/gtest.h>

#include <chrono>
#include <condition_variable>
#include <future>
#include <memory>
#include <mutex>
#include <string>
#include <thread>

#include <control_msgs/action/follow_joint_trajectory.hpp>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <rclcpp/executors/multi_threaded_executor.hpp>

#include "so101_gazebo_demo/pick_place/follow_joint_trajectory_gripper_adapter.hpp"

namespace pick_place = so101_gazebo_demo::pick_place;
using namespace std::chrono_literals;

namespace
{

using Follow = control_msgs::action::FollowJointTrajectory;
using ServerGoalHandle = rclcpp_action::ServerGoalHandle<Follow>;

class ControlledFollowServer
{
public:
  explicit ControlledFollowServer(const std::shared_ptr<rclcpp::Node> & node)
  {
    server_ = rclcpp_action::create_server<Follow>(
      node, "/test_gripper_controller/follow_joint_trajectory",
      [](const rclcpp_action::GoalUUID &, std::shared_ptr<const Follow::Goal>) {
        return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
      },
      [this](const std::shared_ptr<ServerGoalHandle>) {
        {
          std::lock_guard<std::mutex> lock(mutex_);
          cancel_seen_ = true;
        }
        condition_.notify_all();
        return rclcpp_action::CancelResponse::ACCEPT;
      },
      [this](const std::shared_ptr<ServerGoalHandle> handle) {
        {
          std::lock_guard<std::mutex> lock(mutex_);
          goal_ = handle;
        }
        condition_.notify_all();
      });
  }

  bool waitForCancel(std::chrono::milliseconds timeout)
  {
    std::unique_lock<std::mutex> lock(mutex_);
    return condition_.wait_for(lock, timeout, [this]() { return cancel_seen_; });
  }

  void finishCancelled()
  {
    std::shared_ptr<ServerGoalHandle> goal;
    {
      std::lock_guard<std::mutex> lock(mutex_);
      goal = goal_;
    }
    ASSERT_TRUE(goal);
    auto result = std::make_shared<Follow::Result>();
    result->error_code = Follow::Result::SUCCESSFUL;
    goal->canceled(result);
  }

  void finishAborted()
  {
    std::shared_ptr<ServerGoalHandle> goal;
    {
      std::lock_guard<std::mutex> lock(mutex_);
      goal = goal_;
    }
    ASSERT_TRUE(goal);
    auto result = std::make_shared<Follow::Result>();
    result->error_code = Follow::Result::PATH_TOLERANCE_VIOLATED;
    goal->abort(result);
  }

private:
  std::mutex mutex_;
  std::condition_variable condition_;
  bool cancel_seen_{false};
  std::shared_ptr<ServerGoalHandle> goal_;
  rclcpp_action::Server<Follow>::SharedPtr server_;
};

class RosTrajectoryActionClientTest : public ::testing::Test
{
protected:
  void SetUp() override
  {
    if (!rclcpp::ok()) {
      rclcpp::init(0, nullptr);
    }
    server_node_ = std::make_shared<rclcpp::Node>("controlled_gripper_server");
    client_node_ = std::make_shared<rclcpp::Node>("controlled_gripper_client");
    server_ = std::make_unique<ControlledFollowServer>(server_node_);
    executor_ = std::make_unique<rclcpp::executors::MultiThreadedExecutor>();
    executor_->add_node(server_node_);
    executor_->add_node(client_node_);
    spin_thread_ = std::thread([this]() { executor_->spin(); });
  }

  void TearDown() override
  {
    executor_->cancel();
    if (spin_thread_.joinable()) {
      spin_thread_.join();
    }
    executor_->remove_node(client_node_);
    executor_->remove_node(server_node_);
    executor_.reset();
    server_.reset();
    client_node_.reset();
    server_node_.reset();
  }

  pick_place::SingleJointTrajectoryGoal goal() const
  {
    return {{"6"}, {0.7}, 0.1};
  }

  std::unique_ptr<rclcpp::executors::MultiThreadedExecutor> executor_;
  std::shared_ptr<rclcpp::Node> server_node_;
  std::shared_ptr<rclcpp::Node> client_node_;
  std::unique_ptr<ControlledFollowServer> server_;
  std::thread spin_thread_;
};

TEST_F(RosTrajectoryActionClientTest, CancelWaitsForOriginalGoalTerminalResult)
{
  pick_place::RosTrajectoryActionClient client(
    client_node_, "/test_gripper_controller/follow_joint_trajectory");
  const auto send = client.send(goal(), 0.15);
  ASSERT_EQ(pick_place::ActionStatus::TIMED_OUT, send.status);

  auto cancelled = std::async(std::launch::async, [&client]() { return client.cancelAndWait(1.0); });
  ASSERT_TRUE(server_->waitForCancel(500ms));
  EXPECT_EQ(std::future_status::timeout, cancelled.wait_for(100ms));

  server_->finishCancelled();
  ASSERT_EQ(std::future_status::ready, cancelled.wait_for(500ms));
  EXPECT_EQ(pick_place::ActionStatus::SUCCEEDED, cancelled.get().status);
}

TEST_F(RosTrajectoryActionClientTest, CancelTimesOutWhenOriginalGoalNeverBecomesTerminal)
{
  pick_place::RosTrajectoryActionClient client(
    client_node_, "/test_gripper_controller/follow_joint_trajectory");
  ASSERT_EQ(pick_place::ActionStatus::TIMED_OUT, client.send(goal(), 0.1).status);

  const auto cancelled = client.cancelAndWait(0.2);

  EXPECT_EQ(pick_place::ActionStatus::TIMED_OUT, cancelled.status);
  ASSERT_TRUE(cancelled.failure);
  EXPECT_EQ("GRIPPER_CANCEL_TERMINAL_TIMEOUT", cancelled.failure->code);
  server_->finishCancelled();
  const auto terminal = client.cancelAndWait(0.2);
  EXPECT_EQ(pick_place::ActionStatus::SUCCEEDED, terminal.status);
}

TEST_F(RosTrajectoryActionClientTest, AbortedTerminalResultIsNotCancellationSuccess)
{
  pick_place::RosTrajectoryActionClient client(
    client_node_, "/test_gripper_controller/follow_joint_trajectory");
  ASSERT_EQ(pick_place::ActionStatus::TIMED_OUT, client.send(goal(), 0.1).status);

  auto cancelled = std::async(std::launch::async, [&client]() { return client.cancelAndWait(1.0); });
  ASSERT_TRUE(server_->waitForCancel(500ms));
  server_->finishAborted();
  const auto result = cancelled.get();

  EXPECT_EQ(pick_place::ActionStatus::FAILED, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("GRIPPER_CANCEL_TERMINAL_NOT_CANCELLED", result.failure->code);
}

}  // namespace
