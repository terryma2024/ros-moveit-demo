#pragma once

#include <memory>
#include <string>
#include <vector>

#include "panda_gazebo_demo/pick_place/motion_plan_evidence.hpp"
#include "panda_gazebo_demo/pick_place/state_action.hpp"
#include "panda_gazebo_demo/pick_place/state_validation.hpp"

namespace rclcpp
{
class Node;
}

namespace panda_gazebo_demo::pick_place
{

struct MotionPlanningRequest
{
  State state;
  State next_state;
  MotionKind kind;
  bool carrying;
  Pose3d target_pose;
};

class IMoveItMotionAdapter
{
public:
  virtual ~IMoveItMotionAdapter() = default;
  [[nodiscard]] virtual PlanResult plan(
    const MotionPlanningRequest & request,
    const ObservationResult & observation) = 0;
  [[nodiscard]] virtual ActionResult execute(const MotionPlanEvidence & evidence) = 0;
  [[nodiscard]] virtual ActionResult cancel() = 0;
};

class MoveItMotionAdapter final : public IMoveItMotionAdapter, public IWorldObserver
{
public:
  MoveItMotionAdapter(
    std::shared_ptr<rclcpp::Node> node, std::string planning_group,
    std::string tcp_link, std::vector<std::string> required_world_objects,
    double velocity_scaling, double acceleration_scaling, double cartesian_eef_step,
    double motion_start_joint_tolerance = 0.01,
    double joint_velocity_tolerance = 0.01, GripperLimits gripper_limits = {});
  ~MoveItMotionAdapter() override;

  [[nodiscard]] PlanResult plan(
    const MotionPlanningRequest & request,
    const ObservationResult & observation) override;
  [[nodiscard]] ActionResult execute(const MotionPlanEvidence & evidence) override;
  [[nodiscard]] ActionResult cancel() override;
  [[nodiscard]] ObservationResult observe() override;

private:
  class Impl;
  std::unique_ptr<Impl> impl_;
};

void applyMotionObservationThresholds(
  WorldSnapshot & snapshot, double joint_velocity_tolerance,
  const GripperLimits & gripper_limits);

}  // namespace panda_gazebo_demo::pick_place
