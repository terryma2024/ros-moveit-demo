#include "panda_gazebo_demo/pick_place/move_above_object_planner.hpp"

#include <cmath>
#include <memory>
#include <optional>
#include <utility>

#include <Eigen/Geometry>
#include <geometry_msgs/msg/pose.hpp>
#include <moveit/move_group_interface/move_group_interface.hpp>
#include <moveit/planning_scene_interface/planning_scene_interface.hpp>
#include <moveit/robot_state/conversions.hpp>
#include <moveit/robot_state/robot_state.hpp>

#include "panda_gazebo_demo/pick_place/moveit_world_object_pose.hpp"

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

Pose3d toPose3d(const Eigen::Isometry3d & transform)
{
  const Eigen::Quaterniond orientation(transform.rotation());
  const auto & position = transform.translation();
  return {position.x(), position.y(), position.z(), orientation.x(),
    orientation.y(), orientation.z(), orientation.w()};
}

void logTcpPose(const rclcpp::Logger & logger, const char * label, const Pose3d & pose)
{
  const Eigen::Quaterniond orientation(pose.qw, pose.qx, pose.qy, pose.qz);
  const auto rpy = orientation.normalized().toRotationMatrix().eulerAngles(0, 1, 2);
  RCLCPP_INFO(logger, "%s x=%.6f y=%.6f z=%.6f roll=%.6f pitch=%.6f yaw=%.6f", label, pose.x,
              pose.y, pose.z, rpy.x(), rpy.y(), rpy.z());
}

std::optional<Pose3d> plannedEndTcpPose(
  const MoveGroupInterface & move_group,
  const MoveGroupInterface::Plan & plan,
  const std::string & tcp_link)
{
  const auto robot_model = move_group.getRobotModel();
  const auto & trajectory = plan.trajectory.joint_trajectory;
  if (!robot_model || trajectory.points.empty()) {
    return std::nullopt;
  }
  moveit::core::RobotState end_state(robot_model);
  if (!moveit::core::robotStateMsgToRobotState(plan.start_state, end_state)) {
    return std::nullopt;
  }
  end_state.setVariablePositions(trajectory.joint_names, trajectory.points.back().positions);
  end_state.update();
  return toPose3d(end_state.getGlobalLinkTransform(tcp_link));
}

geometry_msgs::msg::Pose preGraspPose()
{
  geometry_msgs::msg::Pose pose;
  pose.position.x = 0.3;
  pose.position.y = 0.0;
  pose.position.z = 0.987;
  pose.orientation.x = 1.0;
  pose.orientation.y = 0.0;
  pose.orientation.z = 0.0;
  pose.orientation.w = 0.0;
  return pose;
}

}  // namespace

class MoveAboveObjectPlanner::Impl
{
public:
  std::unique_ptr<MoveGroupInterface> move_group;
};

MoveAboveObjectPlanner::MoveAboveObjectPlanner(
  std::shared_ptr<rclcpp::Node> node,
  std::string planning_group, std::string tcp_link,
  std::vector<std::string> required_world_objects,
  double velocity_scaling,
  double acceleration_scaling)
:node_(std::move(node)), planning_group_(std::move(planning_group)),
  tcp_link_(std::move(tcp_link)), required_world_objects_(std::move(required_world_objects)),
  velocity_scaling_(velocity_scaling), acceleration_scaling_(acceleration_scaling),
  impl_(std::make_unique<Impl>())
{
}

MoveAboveObjectPlanner::~MoveAboveObjectPlanner() = default;

PlanResult MoveAboveObjectPlanner::plan(State state)
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
  const auto target_pose = preGraspPose();
  logTcpPose(node_->get_logger(), "TARGET_TCP_POSE", toPose3d(target_pose));
  if (!move_group.setPoseTarget(target_pose, tcp_link_)) {
    return planningFailure(FailureCategory::PLANNING, "POSE_TARGET_REJECTED",
                           "Failed to set pre-grasp pose target");
  }
  MoveGroupInterface::Plan moveit_plan;
  const bool succeeded = static_cast<bool>(move_group.plan(moveit_plan));
  const auto point_count = moveit_plan.trajectory.joint_trajectory.points.size();
  if (!succeeded || point_count == 0) {
    return planningFailure(FailureCategory::PLANNING, "EMPTY_OR_FAILED_PLAN",
                           "Planning failed or produced an empty trajectory");
  }
  const auto planned_end_pose = plannedEndTcpPose(move_group, moveit_plan, tcp_link_);
  if (!planned_end_pose) {
    return planningFailure(FailureCategory::PLAN_VALIDATION, "PLANNED_END_TCP_POSE_UNAVAILABLE",
                           "Could not compute TCP pose at the planned trajectory endpoint");
  }
  logTcpPose(node_->get_logger(), "PLANNED_END_TCP_POSE", *planned_end_pose);
  RCLCPP_INFO(node_->get_logger(), "%s plan succeeded: %zu trajectory points", toString(state),
              point_count);
  return {{ActionStatus::SUCCEEDED, std::nullopt},
    std::make_shared<MoveItPlanArtifact>(std::move(moveit_plan))};
}

ActionResult MoveAboveObjectPlanner::execute(State state, std::shared_ptr<const PlanArtifact> plan)
{
  if (state != State::MOVE_ABOVE_OBJECT) {
    return executionFailure("STATE_NOT_EXECUTABLE", "Executor only supports MOVE_ABOVE_OBJECT");
  }
  const auto moveit_plan = std::dynamic_pointer_cast<const MoveItPlanArtifact>(std::move(plan));
  if (!moveit_plan || !impl_->move_group) {
    return executionFailure(
      "INVALID_MOVEIT_PLAN_ARTIFACT",
      "MOVE_ABOVE_OBJECT execution requires a MoveIt trajectory from this planner");
  }
  const bool executed = static_cast<bool>(impl_->move_group->execute(moveit_plan->plan));
  if (!executed) {
    return executionFailure("MOVEIT_EXECUTION_FAILED",
                            "MoveIt failed to execute the pre-grasp trajectory");
  }
  logTcpPose(node_->get_logger(), "EXECUTED_END_TCP_POSE",
             toPose3d(impl_->move_group->getCurrentPose(tcp_link_).pose));
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ActionResult MoveAboveObjectPlanner::cancel()
{
  if (impl_->move_group) {
    impl_->move_group->stop();
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ObservationResult MoveAboveObjectPlanner::observe()
{
  if (!impl_->move_group) {
    impl_->move_group = std::make_unique<MoveGroupInterface>(node_, planning_group_);
  }
  auto & move_group = *impl_->move_group;
  if (!move_group.startStateMonitor(2.0)) {
    return {std::nullopt, Failure{FailureCategory::OBSERVATION,
        "STATE_MONITOR_UNAVAILABLE",
        "Failed to start MoveIt current-state monitor",
        {}}};
  }
  if (!move_group.setEndEffectorLink(tcp_link_)) {
    return {std::nullopt, Failure{FailureCategory::CONFIGURATION,
        "INVALID_TCP_LINK",
        "MoveIt RobotModel does not accept " + tcp_link_,
        {}}};
  }
  const auto state = move_group.getCurrentState(2.0);
  if (!state) {
    return {std::nullopt, Failure{FailureCategory::OBSERVATION,
        "CURRENT_STATE_UNAVAILABLE",
        "MoveIt did not provide a current robot state",
        {}}};
  }
  WorldSnapshot snapshot;
  snapshot.observed_at = std::chrono::steady_clock::now();
  snapshot.fresh = true;
  snapshot.tcp_pose_world = toPose3d(move_group.getCurrentPose(tcp_link_).pose);
  snapshot.arm_stationary = true;
  for (const auto & variable : state->getVariableNames()) {
    snapshot.joint_positions[variable] = state->getVariablePosition(variable);
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
    snapshot.moveit_world_object_poses.emplace(object_id, worldPoseFromCollisionObject(object));
  }
  snapshot.moveit_coke_attached = planning_scene.getAttachedObjects({"coke"}).count("coke") != 0;
  return {snapshot, std::nullopt};
}

}  // namespace panda_gazebo_demo::pick_place
