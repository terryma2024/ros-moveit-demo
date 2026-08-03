#pragma once

#include <memory>
#include <thread>
#include <utility>

#include <rclcpp/executors/single_threaded_executor.hpp>
#include <rclcpp/node.hpp>

namespace so101_gazebo_demo::pick_place
{

class NodeSpinner
{
public:
  explicit NodeSpinner(std::shared_ptr<rclcpp::Node> node) : node_(std::move(node))
  {
    executor_.add_node(node_);
    thread_ = std::thread([this]() { executor_.spin(); });
  }

  ~NodeSpinner()
  {
    executor_.cancel();
    if (thread_.joinable())
      thread_.join();
    executor_.remove_node(node_);
  }

  NodeSpinner(const NodeSpinner &) = delete;
  NodeSpinner & operator=(const NodeSpinner &) = delete;

private:
  std::shared_ptr<rclcpp::Node> node_;
  rclcpp::executors::SingleThreadedExecutor executor_;
  std::thread thread_;
};

}  // namespace so101_gazebo_demo::pick_place
