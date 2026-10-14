// Copyright 2026 SO-101 maintainers
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Local test (not part of the upstream package): the controller_state stream must not lose ticks when the thread that
// publishes it is late. Every update() of the controller produces one state message; every one of them must reach a
// subscriber, once and in order.

#include <chrono>
#include <cstdint>
#include <mutex>
#include <thread>
#include <vector>

#include "control_msgs/msg/joint_trajectory_controller_state.hpp"
#include "rclcpp/executors/single_threaded_executor.hpp"
#include "rclcpp/qos.hpp"

#include "joint_trajectory_controller/joint_trajectory_controller.hpp"
#include "test_trajectory_controller_utils.hpp"

using control_msgs::msg::JointTrajectoryControllerState;
using test_trajectory_controllers::TrajectoryControllerTest;

namespace
{
constexpr int64_t kBaseNs = 1000000000LL;
constexpr int64_t kPeriodNs = 2000000LL;  // 500 Hz
int64_t stamp_ns(const JointTrajectoryControllerState & message)
{
  return static_cast<int64_t>(message.header.stamp.sec) * 1000000000LL + message.header.stamp.nanosec;
}
}  // namespace

class StateQueuePublicationTest : public TrajectoryControllerTest
{
protected:
  /// Runs `updates` back-to-back update() calls (no sleeping, so the publishing thread cannot keep pace) and returns
  /// the stamps that reach a subscriber, in arrival order.
  std::vector<int64_t> run(int updates)
  {
    rclcpp::executors::SingleThreadedExecutor executor;
    SetUpAndActivateTrajectoryController(executor, {});
    std::mutex mutex;
    std::vector<int64_t> stamps;
    auto qos = rclcpp::QoS(rclcpp::KeepLast(20000)).reliable();
    auto subscription = traj_controller_->get_node()->create_subscription<JointTrajectoryControllerState>(
      controller_name_ + "/controller_state", qos,
      [&](const JointTrajectoryControllerState & message)
      {
        std::lock_guard<std::mutex> guard(mutex);
        stamps.push_back(stamp_ns(message));
      });
    const auto settle = std::chrono::steady_clock::now() + std::chrono::milliseconds(100);
    while (std::chrono::steady_clock::now() < settle)
    {
      executor.spin_some();
    }
    {
      std::lock_guard<std::mutex> guard(mutex);
      stamps.clear();  // anything from activation is not part of the measured burst
    }
    for (int i = 0; i < updates; ++i)
    {
      const rclcpp::Time now(kBaseNs + static_cast<int64_t>(i) * kPeriodNs, RCL_ROS_TIME);
      traj_controller_->update(now, rclcpp::Duration::from_nanoseconds(kPeriodNs));
      mirrorCommandToStateIfNotSeparate();
      if (i % 25 == 24)
      {
        // Paced in bursts so the DDS layer (history depth 10) is not what this test measures.
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
        executor.spin_some();
      }
    }
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(10);
    while (std::chrono::steady_clock::now() < deadline)
    {
      executor.spin_some();
      std::lock_guard<std::mutex> guard(mutex);
      if (stamps.size() >= static_cast<std::size_t>(updates))
      {
        break;
      }
    }
    std::lock_guard<std::mutex> guard(mutex);
    return stamps;
  }
};

TEST_F(StateQueuePublicationTest, every_update_reaches_the_subscriber_once_and_in_order)
{
  constexpr int kUpdates = 1500;
  const auto stamps = run(kUpdates);
  std::vector<int64_t> expected;
  for (int i = 0; i < kUpdates; ++i)
  {
    expected.push_back(kBaseNs + static_cast<int64_t>(i) * kPeriodNs);
  }
  EXPECT_EQ(stamps.size(), expected.size()) << "lost " << (expected.size() - stamps.size()) << " of " << kUpdates;
  EXPECT_EQ(stamps, expected);
}

TEST_F(StateQueuePublicationTest, the_counters_account_for_every_message)
{
  constexpr int kUpdates = 600;
  const auto stamps = run(kUpdates);
  ASSERT_EQ(stamps.size(), static_cast<std::size_t>(kUpdates));
  const auto settle = std::chrono::steady_clock::now() + std::chrono::seconds(2);
  while (traj_controller_->state_publisher_stats().published !=
           traj_controller_->state_publisher_stats().enqueued &&
         std::chrono::steady_clock::now() < settle)
  {
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  const auto stats = traj_controller_->state_publisher_stats();
  // activation may add messages before the measured burst, so the counters are at least the burst
  EXPECT_GE(stats.enqueued, static_cast<uint64_t>(kUpdates));
  EXPECT_EQ(stats.published, stats.enqueued);
  EXPECT_EQ(stats.overflowed, 0U);
  EXPECT_EQ(stats.sink_errors, 0U);
}
