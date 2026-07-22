#include "panda_gazebo_demo/pick_place/moveit_pregrasp_planner.hpp"

#include <algorithm>
#include <cmath>
#include <memory>
#include <utility>

#include <geometry_msgs/msg/pose.hpp>
#include <moveit/move_group_interface/move_group_interface.hpp>
#include <moveit/planning_scene_interface/planning_scene_interface.hpp>

namespace panda_gazebo_demo::pick_place
{

namespace
{

using MoveGroupInterface = moveit::planning_interface::MoveGroupInterface;

class MoveItPlanArtifact final : public PlanArtifact
{
public:
  explicit MoveItPlanArtifact(MoveGroupInterface::Plan moveit_plan)
  : plan(std::move(moveit_plan))
  {
    trajectory_points = plan.trajectory.joint_trajectory.points.size();
  }

  MoveGroupInterface::Plan plan;
};

PlanResult planningFailure(FailureCategory category, std::string code, std::string message)
{
  return {{ActionStatus::FAILED, Failure{category, std::move(code), std::move(message), {}}},
    nullptr};
}

ActionResult executionFailure(std::string code, std::string message)
{
  return {ActionStatus::FAILED,
    Failure{FailureCategory::EXECUTION, std::move(code), std::move(message), {}}};
}

Pose3d toPose3d(const geometry_msgs::msg::Pose & pose)
{
  return {pose.position.x, pose.position.y, pose.position.z, pose.orientation.x,
    pose.orientation.y, pose.orientation.z, pose.orientation.w};
}

geometry_msgs::msg::Pose preGraspPose()
{
  geometry_msgs::msg::Pose pose;
  pose.position.x = 0.3;
  pose.position.y = 0.0;
  pose.position.z = 0.987;
  pose.orientation.x = 1.0;
  return pose;
}

}  // namespace

class MoveItPreGraspPlanner::Impl
{
public:
  std::unique_ptr<MoveGroupInterface> move_group;
};

MoveItPreGraspPlanner::MoveItPreGraspPlanner(
  std::shared_ptr<rclcpp::Node> node, std::string planning_group,
  std::string tcp_link, std::vector<std::string> required_world_objects,
  double velocity_scaling, double acceleration_scaling)
: node_(std::move(node)), planning_group_(std::move(planning_group)),
  tcp_link_(std::move(tcp_link)), required_world_objects_(std::move(required_world_objects)),
  velocity_scaling_(velocity_scaling), acceleration_scaling_(acceleration_scaling),
  impl_(std::make_unique<Impl>())
{
}

MoveItPreGraspPlanner::~MoveItPreGraspPlanner() = default;

PlanResult MoveItPreGraspPlanner::plan(State state)
{
  if (state != State::MOVE_ABOVE_OBJECT) {
    return planningFailure(FailureCategory::PLANNING, "STATE_NOT_PLANNABLE",
        "Planner only supports MOVE_ABOVE_OBJECT");
  }
  if (!impl_->move_group) {
    impl_->move_group = std::make_unique<MoveGroupInterface>(node_, planning_group_);
  }
  auto & move_group = *impl_->move_group;
  moveit::planning_interface::PlanningSceneInterface planning_scene;
  const auto world_objects = planning_scene.getObjects(required_world_objects_);
  for (const auto & object_id : required_world_objects_) {
    if (world_objects.count(object_id) == 0) {
      return planningFailure(FailureCategory::MOVEIT_SCENE, "REQUIRED_WORLD_OBJECT_MISSING",
                             "Required Planning Scene world object is missing: " + object_id);
    }
  }
  if (!move_group.startStateMonitor(2.0)) {
    return planningFailure(FailureCategory::OBSERVATION, "STATE_MONITOR_UNAVAILABLE",
                           "Failed to start MoveIt current-state monitor");
  }
  move_group.setPoseReferenceFrame("world");
  move_group.setMaxVelocityScalingFactor(velocity_scaling_);
  move_group.setMaxAccelerationScalingFactor(acceleration_scaling_);
  if (!move_group.setEndEffectorLink(tcp_link_)) {
    return planningFailure(FailureCategory::CONFIGURATION, "INVALID_TCP_LINK",
                           "MoveIt RobotModel does not accept " + tcp_link_);
  }
  move_group.clearPoseTargets();
  move_group.setStartStateToCurrentState();
  if (!move_group.setPoseTarget(preGraspPose(), tcp_link_)) {
    return planningFailure(FailureCategory::PLANNING, "POSE_TARGET_REJECTED",
                           "Failed to set pre-grasp pose target");
  }
  MoveGroupInterface::Plan moveit_plan;
  const bool succeeded = static_cast<bool>(move_group.plan(moveit_plan));
  const auto point_count = moveit_plan.trajectory.joint_trajectory.points.size();
  if (!succeeded || point_count == 0) {
    return planningFailure(FailureCategory::PLANNING, "EMPTY_OR_FAILED_PLAN",
                           "Planning to pre-grasp failed or produced an empty trajectory");
  }
  RCLCPP_INFO(node_->get_logger(), "Pre-grasp plan succeeded: %zu trajectory points", point_count);
  return {{ActionStatus::SUCCEEDED, std::nullopt},
    std::make_shared<MoveItPlanArtifact>(std::move(moveit_plan))};
}

ActionResult MoveItPreGraspPlanner::execute(
  State state, std::shared_ptr<const PlanArtifact> plan)
{
  if (state != State::MOVE_ABOVE_OBJECT) {
    return executionFailure("STATE_NOT_EXECUTABLE", "Executor only supports MOVE_ABOVE_OBJECT");
  }
  const auto moveit_plan = std::dynamic_pointer_cast<const MoveItPlanArtifact>(std::move(plan));
  if (!moveit_plan || !impl_->move_group) {
    return executionFailure("INVALID_MOVEIT_PLAN_ARTIFACT",
      "MOVE_ABOVE_OBJECT execution requires a MoveIt trajectory from this planner");
  }
  const bool executed = static_cast<bool>(impl_->move_group->execute(moveit_plan->plan));
  if (!executed) {
    return executionFailure("MOVEIT_EXECUTION_FAILED",
        "MoveIt failed to execute the pre-grasp trajectory");
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ActionResult MoveItPreGraspPlanner::cancel()
{
  if (impl_->move_group) {
    impl_->move_group->stop();
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ObservationResult MoveItPreGraspPlanner::observe()
{
  if (!impl_->move_group) {
    impl_->move_group = std::make_unique<MoveGroupInterface>(node_, planning_group_);
  }
  auto & move_group = *impl_->move_group;
  if (!move_group.startStateMonitor(2.0)) {
    return {std::nullopt, Failure{FailureCategory::OBSERVATION, "STATE_MONITOR_UNAVAILABLE",
        "Failed to start MoveIt current-state monitor", {}}};
  }
  if (!move_group.setEndEffectorLink(tcp_link_)) {
    return {std::nullopt, Failure{FailureCategory::CONFIGURATION, "INVALID_TCP_LINK",
        "MoveIt RobotModel does not accept " + tcp_link_, {}}};
  }
  const auto state = move_group.getCurrentState(2.0);
  if (!state) {
    return {std::nullopt, Failure{FailureCategory::OBSERVATION, "CURRENT_STATE_UNAVAILABLE",
        "MoveIt did not provide a current robot state", {}}};
  }
  WorldSnapshot snapshot;
  snapshot.observed_at = std::chrono::steady_clock::now();
  snapshot.fresh = true;
  snapshot.tcp_pose_world = toPose3d(move_group.getCurrentPose(tcp_link_).pose);
  snapshot.arm_stationary = true;
  for (const auto & variable : state->getVariableNames()) {
    const auto velocity = state->getVariableVelocity(variable);
    snapshot.joint_velocities[variable] = velocity;
    if (std::abs(velocity) > 0.01) {
      snapshot.arm_stationary = false;
    }
  }
  const auto finger1 = state->getVariablePosition("panda_finger_joint1");
  const auto finger2 = state->getVariablePosition("panda_finger_joint2");
  snapshot.gripper_open = finger1 >= 0.02 && finger2 >= 0.02;

  moveit::planning_interface::PlanningSceneInterface planning_scene;
  const auto world_objects = planning_scene.getObjects(required_world_objects_);
  for (const auto & [object_id, object] : world_objects) {
    if (!object.primitive_poses.empty()) {
      snapshot.world_object_poses.emplace(object_id, toPose3d(object.primitive_poses.front()));
    } else if (!object.mesh_poses.empty()) {
      snapshot.world_object_poses.emplace(object_id, toPose3d(object.mesh_poses.front()));
    }
  }
  snapshot.coke_attached = planning_scene.getAttachedObjects({"coke"}).count("coke") != 0;
  return {snapshot, std::nullopt};
}

}  // namespace panda_gazebo_demo::pick_place
