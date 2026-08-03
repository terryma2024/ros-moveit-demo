#pragma once

#include <memory>
#include <string>
#include <vector>

#include <rclcpp/node.hpp>

#include "so101_gazebo_demo/pick_place/follow_joint_trajectory_gripper_adapter.hpp"
#include "so101_gazebo_demo/pick_place/world_reset_coordinator.hpp"

namespace so101_gazebo_demo::pick_place
{

class IArmHomePlanningBoundary
{
public:
  virtual ~IArmHomePlanningBoundary() = default;
  [[nodiscard]] virtual PlanResult planHome(const std::vector<std::string> & joint_names,
                                            const std::vector<double> & goal) = 0;
  [[nodiscard]] virtual ActionResult executeHome(const PlanArtifact & plan) = 0;
  [[nodiscard]] virtual ActionResult cancelAndWait() = 0;
};

class MoveGroupArmHomePlanningBoundary final : public IArmHomePlanningBoundary
{
public:
  MoveGroupArmHomePlanningBoundary(const std::shared_ptr<rclcpp::Node> & node,
                                   const std::string & planning_group, double endpoint_tolerance,
                                   double velocity_scaling = 0.15,
                                   double acceleration_scaling = 0.15);
  ~MoveGroupArmHomePlanningBoundary() override;

  [[nodiscard]] PlanResult planHome(const std::vector<std::string> & joint_names,
                                    const std::vector<double> & goal) override;
  [[nodiscard]] ActionResult executeHome(const PlanArtifact & plan) override;
  [[nodiscard]] ActionResult cancelAndWait() override;

private:
  class Impl;
  std::unique_ptr<Impl> impl_;
};

class MoveItRobotHomeResetAdapter final : public IRobotHomeResetAdapter
{
public:
  MoveItRobotHomeResetAdapter(std::shared_ptr<IArmHomePlanningBoundary> arm,
                              std::shared_ptr<IJointPlanningBoundary> joints,
                              std::shared_ptr<ISO101GripperCommand> gripper,
                              SO101Profile profile = SO101Profile::canonical());

  [[nodiscard]] std::optional<CurrentJointStateEvidence> observeJoints() override;
  [[nodiscard]] ActionResult commandGripper(double q6) override;
  [[nodiscard]] PlanResult planArmHome(const std::vector<double> & goal) override;
  [[nodiscard]] ActionResult executeArmHome(const PlanArtifact & plan) override;
  [[nodiscard]] ActionResult cancelArmAndWait() override;

private:
  std::shared_ptr<IArmHomePlanningBoundary> arm_;
  std::shared_ptr<IJointPlanningBoundary> joints_;
  std::shared_ptr<ISO101GripperCommand> gripper_;
  SO101Profile profile_;
};

}  // namespace so101_gazebo_demo::pick_place
