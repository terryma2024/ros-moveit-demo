#pragma once

#include <memory>
#include <string>

#include <rclcpp/rclcpp.hpp>

#include "panda_gazebo_demo/pick_place/pick_place_target_policy.hpp"
#include "panda_gazebo_demo/pick_place/state_action.hpp"

namespace panda_gazebo_demo::pick_place
{

class DescendPlannerExecutor final : public IStatePlanner, public IStateExecutor
{
public:
  DescendPlannerExecutor(
    std::shared_ptr<rclcpp::Node> node, std::string planning_group,
    std::string tcp_link, std::shared_ptr<const PickPlaceTargetPolicy> target_policy,
    double velocity_scaling, double acceleration_scaling, double eef_step,
    double min_fraction, double joint_jump_threshold, double tcp_position_tolerance,
    double tcp_orientation_tolerance_rad);
  ~DescendPlannerExecutor() override;

  [[nodiscard]] PlanResult plan(
    State current_state, State next_state,
    const ObservationResult & observation) override;
  [[nodiscard]] ActionResult execute(
    State state, std::shared_ptr<const PlanArtifact> plan) override;
  [[nodiscard]] ActionResult cancel() override;

private:
  std::shared_ptr<rclcpp::Node> node_;
  std::string planning_group_;
  std::string tcp_link_;
  std::shared_ptr<const PickPlaceTargetPolicy> target_policy_;
  double velocity_scaling_;
  double acceleration_scaling_;
  double eef_step_;
  double min_fraction_;
  double joint_jump_threshold_;
  double tcp_position_tolerance_;
  double tcp_orientation_tolerance_rad_;
  class Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace panda_gazebo_demo::pick_place
