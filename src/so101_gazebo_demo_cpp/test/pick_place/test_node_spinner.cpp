#include <atomic>
#include <chrono>
#include <memory>
#include <thread>

#include <gtest/gtest.h>
#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/empty.hpp>

#include "so101_gazebo_demo/pick_place/node_spinner.hpp"

namespace spp = so101_gazebo_demo::pick_place;
using namespace std::chrono_literals;

TEST(NodeSpinner, ProcessesCallbacksAndStopsBeforeDestructionReturns)
{
  if (!rclcpp::ok()) {
    int argc = 0;
    rclcpp::init(argc, nullptr);
  }
  auto subscriber_node = std::make_shared<rclcpp::Node>("spinner_subscriber");
  auto publisher_node = std::make_shared<rclcpp::Node>("spinner_publisher");
  std::atomic<int> callbacks{0};
  auto subscription = subscriber_node->create_subscription<std_msgs::msg::Empty>(
    "/so101/test_spinner", 10, [&](const std_msgs::msg::Empty &) { ++callbacks; });
  auto publisher =
    publisher_node->create_publisher<std_msgs::msg::Empty>("/so101/test_spinner", 10);
  {
    spp::NodeSpinner spinner(subscriber_node);
    for (int i = 0; i < 20 && callbacks.load() == 0; ++i) {
      publisher->publish(std_msgs::msg::Empty{});
      std::this_thread::sleep_for(20ms);
    }
    EXPECT_GT(callbacks.load(), 0);
  }
  const int after_stop = callbacks.load();
  for (int i = 0; i < 5; ++i)
    publisher->publish(std_msgs::msg::Empty{});
  std::this_thread::sleep_for(100ms);
  EXPECT_EQ(callbacks.load(), after_stop);
  static_cast<void>(subscription);
  rclcpp::shutdown();
}
