#include "so101_gazebo_demo/pick_place/robot_home_reset_adapter.hpp"

#include <algorithm>
#include <cmath>
#include <map>
#include <utility>

#include <moveit/move_group_interface/move_group_interface.hpp>

namespace so101_gazebo_demo::pick_place
{
namespace
{

PlanResult planFailure(std::string code, std::string message)
{
  return {{ActionStatus::FAILED,
           Failure{FailureCategory::PLANNING, std::move(code), std::move(message), {}}},
          nullptr};
}

ActionResult executionFailure(std::string code, std::string message)
{
  return {ActionStatus::FAILED,
          Failure{FailureCategory::EXECUTION, std::move(code), std::move(message), {}}};
}

class MoveGroupHomePlanArtifact final : public PlanArtifact
{
public:
  moveit::planning_interface::MoveGroupInterface::Plan plan;
};

bool canonicalGoal(const std::vector<double> & actual, const std::vector<double> & expected)
{
  if (actual.size() != expected.size())
    return false;
  for (std::size_t i = 0; i < actual.size(); ++i) {
    if (!std::isfinite(actual[i]) || std::abs(actual[i] - expected[i]) > 1e-12)
      return false;
  }
  return true;
}

}  // namespace

class MoveGroupArmHomePlanningBoundary::Impl
{
public:
  Impl(const std::shared_ptr<rclcpp::Node> & node, const std::string & group, double tolerance,
       double velocity, double acceleration) :
      move_group(node, group), endpoint_tolerance(tolerance)
  {
    move_group.setMaxVelocityScalingFactor(velocity);
    move_group.setMaxAccelerationScalingFactor(acceleration);
  }

  moveit::planning_interface::MoveGroupInterface move_group;
  double endpoint_tolerance;
};

MoveGroupArmHomePlanningBoundary::MoveGroupArmHomePlanningBoundary(
  const std::shared_ptr<rclcpp::Node> & node, const std::string & planning_group,
  double endpoint_tolerance, double velocity_scaling, double acceleration_scaling) :
    impl_(std::make_unique<Impl>(node, planning_group, endpoint_tolerance, velocity_scaling,
                                 acceleration_scaling))
{
}

MoveGroupArmHomePlanningBoundary::~MoveGroupArmHomePlanningBoundary() = default;

PlanResult MoveGroupArmHomePlanningBoundary::planHome(const std::vector<std::string> & joint_names,
                                                      const std::vector<double> & goal)
{
  if (joint_names.empty() || joint_names.size() != goal.size() ||
      !std::isfinite(impl_->endpoint_tolerance) || impl_->endpoint_tolerance < 0.0) {
    return planFailure("ARM_HOME_REQUEST_INVALID",
                       "Arm home request must contain finite matching joints and goals");
  }
  std::map<std::string, double> target;
  for (std::size_t i = 0; i < joint_names.size(); ++i) {
    if (!std::isfinite(goal[i])) {
      return planFailure("ARM_HOME_REQUEST_INVALID", "Arm home goal must be finite");
    }
    target.emplace(joint_names[i], goal[i]);
  }
  impl_->move_group.setStartStateToCurrentState();
  if (!impl_->move_group.setJointValueTarget(target)) {
    return planFailure("ARM_HOME_TARGET_REJECTED", "MoveIt rejected the arm home joint target");
  }
  auto artifact = std::make_shared<MoveGroupHomePlanArtifact>();
  const auto code = impl_->move_group.plan(artifact->plan);
  if (!code) {
    return planFailure("ARM_HOME_PLAN_FAILED",
                       "MoveIt could not plan a collision-free arm home path");
  }
  const auto & trajectory = artifact->plan.trajectory.joint_trajectory;
  if (trajectory.points.empty()) {
    return planFailure("ARM_HOME_PLAN_EMPTY", "MoveIt returned an empty arm home trajectory");
  }
  const auto & endpoint = trajectory.points.back().positions;
  for (std::size_t i = 0; i < joint_names.size(); ++i) {
    const auto name =
      std::find(trajectory.joint_names.begin(), trajectory.joint_names.end(), joint_names[i]);
    if (name == trajectory.joint_names.end()) {
      return planFailure("ARM_HOME_PLAN_INCOMPLETE", "Arm home trajectory omits a required joint");
    }
    const auto index =
      static_cast<std::size_t>(std::distance(trajectory.joint_names.begin(), name));
    if (index >= endpoint.size() || !std::isfinite(endpoint[index]) ||
        std::abs(endpoint[index] - goal[i]) > impl_->endpoint_tolerance) {
      return planFailure("ARM_HOME_PLAN_ENDPOINT_INVALID",
                         "Arm home trajectory endpoint does not reach the canonical goal");
    }
  }
  artifact->trajectory_points = trajectory.points.size();
  return {{ActionStatus::SUCCEEDED, std::nullopt}, artifact};
}

ActionResult MoveGroupArmHomePlanningBoundary::executeHome(const PlanArtifact & plan)
{
  const auto * artifact = dynamic_cast<const MoveGroupHomePlanArtifact *>(&plan);
  if (!artifact || artifact->trajectory_points == 0) {
    return executionFailure("ARM_HOME_PLAN_ARTIFACT_INVALID",
                            "Arm home execution requires the exact validated MoveIt plan");
  }
  const auto code = impl_->move_group.execute(artifact->plan);
  if (!code) {
    return executionFailure("ARM_HOME_EXECUTION_FAILED",
                            "MoveIt failed to execute the arm home trajectory");
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ActionResult MoveGroupArmHomePlanningBoundary::cancelAndWait()
{
  impl_->move_group.stop();
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

MoveItRobotHomeResetAdapter::MoveItRobotHomeResetAdapter(
  std::shared_ptr<IArmHomePlanningBoundary> arm, std::shared_ptr<IJointPlanningBoundary> joints,
  std::shared_ptr<ISO101GripperCommand> gripper, SO101Profile profile) :
    arm_(std::move(arm)), joints_(std::move(joints)), gripper_(std::move(gripper)),
    profile_(std::move(profile))
{
}

std::optional<CurrentJointStateEvidence> MoveItRobotHomeResetAdapter::observeJoints()
{
  return joints_ ? joints_->currentState() : std::nullopt;
}

ActionResult MoveItRobotHomeResetAdapter::commandGripper(double q6)
{
  if (!gripper_) {
    return executionFailure("GRIPPER_HOME_ADAPTER_MISSING",
                            "Robot home reset requires a gripper command adapter");
  }
  return gripper_->command(q6);
}

PlanResult MoveItRobotHomeResetAdapter::planArmHome(const std::vector<double> & goal)
{
  if (!arm_) {
    return planFailure("ARM_HOME_ADAPTER_MISSING",
                       "Robot home reset requires an arm planning adapter");
  }
  if (!canonicalGoal(goal, profile_.arm_home_positions)) {
    return planFailure("ARM_HOME_TARGET_INVALID",
                       "Arm reset target must equal the canonical SRDF home state");
  }
  return arm_->planHome(profile_.arm_joints, goal);
}

ActionResult MoveItRobotHomeResetAdapter::executeArmHome(const PlanArtifact & plan)
{
  return arm_ ? arm_->executeHome(plan)
              : executionFailure("ARM_HOME_ADAPTER_MISSING",
                                 "Robot home reset requires an arm execution adapter");
}

ActionResult MoveItRobotHomeResetAdapter::cancelArmAndWait()
{
  if (!arm_ || !gripper_) {
    return executionFailure("ROBOT_HOME_ADAPTER_MISSING",
                            "Robot home cancellation requires arm and gripper adapters");
  }
  auto arm = arm_->cancelAndWait();
  if (arm.status != ActionStatus::SUCCEEDED)
    return arm;
  return gripper_->cancelAndWait();
}

}  // namespace so101_gazebo_demo::pick_place
