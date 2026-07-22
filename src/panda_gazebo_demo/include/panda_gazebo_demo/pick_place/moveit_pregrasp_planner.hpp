#pragma once

#include <memory>
#include <string>
#include <vector>

#include <rclcpp/rclcpp.hpp>

#include "panda_gazebo_demo/pick_place/state_action.hpp"
#include "panda_gazebo_demo/pick_place/world_observer.hpp"

namespace panda_gazebo_demo::pick_place
{

class MoveItPreGraspPlanner final : public IStatePlanner, public IStateExecutor,
  public IWorldObserver
{
public:
  MoveItPreGraspPlanner(
    std::shared_ptr<rclcpp::Node> node, std::string planning_group,
    std::string tcp_link, std::vector<std::string> required_world_objects,
    double velocity_scaling, double acceleration_scaling);
  ~MoveItPreGraspPlanner() override;

  [[nodiscard]] PlanResult plan(State state) override;
  [[nodiscard]] ActionResult execute(
    State state, std::shared_ptr<const PlanArtifact> plan) override;
  [[nodiscard]] ActionResult cancel() override;
  [[nodiscard]] ObservationResult observe() override;

private:
  std::shared_ptr<rclcpp::Node> node_;
  std::string planning_group_;
  std::string tcp_link_;
  std::vector<std::string> required_world_objects_;
  double velocity_scaling_;
  double acceleration_scaling_;
  class Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace panda_gazebo_demo::pick_place
