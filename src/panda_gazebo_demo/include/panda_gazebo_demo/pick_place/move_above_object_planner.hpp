#pragma once

#include <memory>
#include <string>
#include <vector>

#include <rclcpp/rclcpp.hpp>

#include "panda_gazebo_demo/pick_place/pick_place_target_policy.hpp"
#include "panda_gazebo_demo/pick_place/state_action.hpp"
#include "panda_gazebo_demo/pick_place/world_observer.hpp"

namespace panda_gazebo_demo::pick_place
{

class MoveAboveObjectPlanner final : public IStatePlanner,
                                     public IStateExecutor,
                                     public IWorldObserver
{
public:
  MoveAboveObjectPlanner(std::shared_ptr<rclcpp::Node> node, std::string planning_group,
                         std::string tcp_link, std::vector<std::string> required_world_objects,
                         std::shared_ptr<const PickPlaceTargetPolicy> target_policy,
                         double velocity_scaling, double acceleration_scaling);
  ~MoveAboveObjectPlanner() override;

  [[nodiscard]] PlanResult plan(State current_state, State next_state,
                                const ObservationResult & observation) override;
  [[nodiscard]] ActionResult execute(const ExecutionContext & context) override;
  [[nodiscard]] ActionResult cancel() override;
  [[nodiscard]] ObservationResult observe() override;

private:
  class Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace panda_gazebo_demo::pick_place
