#pragma once

#include <memory>
#include <string>

#include <rclcpp/rclcpp.hpp>

#include "panda_gazebo_demo/pick_place/state_action.hpp"

namespace panda_gazebo_demo::pick_place
{

class OpenGripperExecutor final : public IStateExecutor
{
public:
  OpenGripperExecutor(
    std::shared_ptr<rclcpp::Node> node, std::string action_name, double open_position,
    double max_effort, double action_timeout_seconds);
  ~OpenGripperExecutor() override;

  [[nodiscard]] ActionResult execute(
    State state, std::shared_ptr<const PlanArtifact> plan) override;
  [[nodiscard]] ActionResult cancel() override;

private:
  class Impl;
  std::shared_ptr<rclcpp::Node> node_;
  std::string action_name_;
  double open_position_;
  double max_effort_;
  double action_timeout_seconds_;
  std::unique_ptr<Impl> impl_;
};

}  // namespace panda_gazebo_demo::pick_place
