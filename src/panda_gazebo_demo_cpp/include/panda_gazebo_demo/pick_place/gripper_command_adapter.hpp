#pragma once

#include <memory>
#include <string>

#include "panda_gazebo_demo/pick_place/domain_types.hpp"

namespace rclcpp
{
class Node;
}  // namespace rclcpp

namespace panda_gazebo_demo::pick_place
{

class IGripperCommandAdapter
{
public:
  virtual ~IGripperCommandAdapter() = default;
  [[nodiscard]] virtual ActionResult command(double position, double max_effort) = 0;
  [[nodiscard]] virtual ActionResult cancelAndWait() = 0;
};

class GripperCommandAdapter final : public IGripperCommandAdapter
{
public:
  GripperCommandAdapter(std::shared_ptr<rclcpp::Node> node, std::string action_name,
                        double action_timeout_seconds);
  ~GripperCommandAdapter() override;

  [[nodiscard]] ActionResult command(double position, double max_effort) override;
  [[nodiscard]] ActionResult cancelAndWait() override;

private:
  class Impl;
  std::shared_ptr<rclcpp::Node> node_;
  std::string action_name_;
  double action_timeout_seconds_;
  std::unique_ptr<Impl> impl_;
};

}  // namespace panda_gazebo_demo::pick_place
