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

// Local test (not part of the upstream package): the joint_states stream must not lose ticks when the thread that
// publishes it is late. Every update() produces one message; every one of them must reach a subscriber, in order.

#include <chrono>
#include <cstdint>
#include <mutex>
#include <thread>
#include <vector>

#include "rclcpp/executors/single_threaded_executor.hpp"
#include "rclcpp/qos.hpp"
#include "sensor_msgs/msg/joint_state.hpp"

#include "test_joint_state_broadcaster.hpp"

namespace
{
constexpr int64_t kBaseNs = 1000000000LL;
constexpr int64_t kPeriodNs = 10000000LL;  // 100 Hz
}  // namespace

TEST_F(JointStateBroadcasterTest, every_update_reaches_the_subscriber_once_and_in_order)
{
  SetUpStateBroadcaster();
  ASSERT_TRUE(configure_succeeds(state_broadcaster_));
  ASSERT_TRUE(activate_succeeds(state_broadcaster_));

  std::mutex mutex;
  std::vector<int64_t> stamps;
  rclcpp::Node test_node("jsb_queue_test_node");
  auto subscription = test_node.create_subscription<sensor_msgs::msg::JointState>(
    "joint_states", rclcpp::QoS(rclcpp::KeepLast(20000)).reliable(),
    [&](const sensor_msgs::msg::JointState & message)
    {
      std::lock_guard<std::mutex> guard(mutex);
      stamps.push_back(
        static_cast<int64_t>(message.header.stamp.sec) * 1000000000LL + message.header.stamp.nanosec);
    });
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(test_node.get_node_base_interface());
  const auto settle = std::chrono::steady_clock::now() + std::chrono::milliseconds(100);
  while (std::chrono::steady_clock::now() < settle)
  {
    executor.spin_some();
  }

  constexpr int kUpdates = 1500;
  std::vector<int64_t> expected;
  for (int i = 0; i < kUpdates; ++i)
  {
    const int64_t stamp = kBaseNs + static_cast<int64_t>(i) * kPeriodNs;
    expected.push_back(stamp);
    state_broadcaster_->update(
      rclcpp::Time(stamp, RCL_ROS_TIME), rclcpp::Duration::from_nanoseconds(kPeriodNs));
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
    if (stamps.size() >= expected.size())
    {
      break;
    }
  }
  std::lock_guard<std::mutex> guard(mutex);
  EXPECT_EQ(stamps.size(), expected.size()) << "lost " << (expected.size() - stamps.size()) << " of " << kUpdates;
  EXPECT_EQ(stamps, expected);
}
