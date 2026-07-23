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
  DescendPlannerExecutor(std::shared_ptr<rclcpp::Node> node, std::string planning_group,
                         std::string tcp_link,
                         std::shared_ptr<const PickPlaceTargetPolicy> target_policy,
                         double velocity_scaling, double acceleration_scaling, double eef_step,
                         double min_fraction, double joint_jump_threshold,
                         double tcp_position_tolerance, double tcp_orientation_tolerance_rad);
  ~DescendPlannerExecutor() override;

  [[nodiscard]] PlanResult plan(State current_state, State next_state,
                                const ObservationResult & observation) override;
  [[nodiscard]] ActionResult execute(const ExecutionContext & context) override;
  [[nodiscard]] ActionResult cancel() override;

private:
  class Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace panda_gazebo_demo::pick_place
