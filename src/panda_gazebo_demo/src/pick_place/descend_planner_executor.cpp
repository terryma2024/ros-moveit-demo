#include "panda_gazebo_demo/pick_place/descend_planner_executor.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <memory>
#include <optional>
#include <utility>
#include <vector>

#include <Eigen/Geometry>
#include <geometry_msgs/msg/pose.hpp>
#include <moveit/move_group_interface/move_group_interface.hpp>
#include <moveit/robot_state/robot_state.hpp>
#include <moveit_msgs/msg/robot_trajectory.hpp>

#include "panda_gazebo_demo/pick_place/cartesian_plan_validation.hpp"

namespace panda_gazebo_demo::pick_place
{

namespace
{

using MoveGroupInterface = moveit::planning_interface::MoveGroupInterface;

class DescendPlanArtifact final : public PlanArtifact
{
public:
  explicit DescendPlanArtifact(moveit_msgs::msg::RobotTrajectory moveit_trajectory)
  : trajectory(std::move(moveit_trajectory))
  {
    trajectory_points = trajectory.joint_trajectory.points.size();
  }

  moveit_msgs::msg::RobotTrajectory trajectory;
};

PlanResult planningFailure(Failure failure)
{
  return {{ActionStatus::FAILED, std::move(failure)}, nullptr};
}

PlanResult planningFailure(FailureCategory category, std::string code, std::string message)
{
  return planningFailure({category, std::move(code), std::move(message), {}});
}

ActionResult executionFailure(std::string code, std::string message)
{
  return {ActionStatus::FAILED,
    Failure{FailureCategory::EXECUTION, std::move(code), std::move(message), {}}};
}

geometry_msgs::msg::Pose toGeometryPose(const Pose3d & pose)
{
  geometry_msgs::msg::Pose result;
  result.position.x = pose.x;
  result.position.y = pose.y;
  result.position.z = pose.z;
  result.orientation.x = pose.qx;
  result.orientation.y = pose.qy;
  result.orientation.z = pose.qz;
  result.orientation.w = pose.qw;
  return result;
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
  return {position.x(), position.y(), position.z(), orientation.x(), orientation.y(),
    orientation.z(), orientation.w()};
}

void logPose(const rclcpp::Logger & logger, const char * label, const Pose3d & pose)
{
  const Eigen::Quaterniond orientation(pose.qw, pose.qx, pose.qy, pose.qz);
  const auto rpy = orientation.normalized().toRotationMatrix().eulerAngles(0, 1, 2);
  RCLCPP_INFO(logger, "%s x=%.6f y=%.6f z=%.6f roll=%.6f pitch=%.6f yaw=%.6f", label,
    pose.x, pose.y, pose.z, rpy.x(), rpy.y(), rpy.z());
}

std::optional<CartesianPlanEvidence> makeEvidence(
  const moveit_msgs::msg::RobotTrajectory & trajectory,
  const moveit::core::RobotState & start_state, const Pose3d & start_tcp_pose,
  const std::string & tcp_link, double fraction)
{
  const auto & joint_trajectory = trajectory.joint_trajectory;
  CartesianPlanEvidence evidence;
  evidence.fraction = fraction;
  evidence.trajectory_points = joint_trajectory.points.size();
  evidence.start_tcp_pose = start_tcp_pose;
  std::int64_t previous_time_nanoseconds = -1;
  evidence.time_parameterized = !joint_trajectory.points.empty();
  moveit::core::RobotState state(start_state);
  std::vector<double> previous_positions;
  previous_positions.reserve(joint_trajectory.joint_names.size());
  for (const auto & joint_name : joint_trajectory.joint_names) {
    previous_positions.push_back(state.getVariablePosition(joint_name));
  }
  for (const auto & point : joint_trajectory.points) {
    const auto time_nanoseconds = static_cast<std::int64_t>(point.time_from_start.sec) *
      1000000000LL + point.time_from_start.nanosec;
    if (time_nanoseconds < 0 ||
      (previous_time_nanoseconds >= 0 && time_nanoseconds <= previous_time_nanoseconds))
    {
      evidence.time_parameterized = false;
    }
    previous_time_nanoseconds = time_nanoseconds;
    if (point.positions.size() != joint_trajectory.joint_names.size()) {
      return std::nullopt;
    }
    for (std::size_t index = 0; index < point.positions.size(); ++index) {
      evidence.max_joint_delta = std::max(
        evidence.max_joint_delta, std::abs(point.positions[index] - previous_positions[index]));
    }
    state.setVariablePositions(joint_trajectory.joint_names, point.positions);
    state.update();
    evidence.tcp_path.push_back(toPose3d(state.getGlobalLinkTransform(tcp_link)));
    previous_positions = point.positions;
  }
  if (previous_time_nanoseconds <= 0) {
    evidence.time_parameterized = false;
  }
  return evidence;
}

}  // namespace

class DescendPlannerExecutor::Impl
{
public:
  std::unique_ptr<MoveGroupInterface> move_group;
};

DescendPlannerExecutor::DescendPlannerExecutor(
  std::shared_ptr<rclcpp::Node> node, std::string planning_group,
  std::string tcp_link, std::shared_ptr<const PickPlaceTargetPolicy> target_policy,
  double velocity_scaling, double acceleration_scaling, double eef_step,
  double min_fraction, double joint_jump_threshold, double tcp_position_tolerance,
  double tcp_orientation_tolerance_rad)
: node_(std::move(node)), planning_group_(std::move(planning_group)),
  tcp_link_(std::move(tcp_link)), target_policy_(std::move(target_policy)),
  velocity_scaling_(velocity_scaling), acceleration_scaling_(acceleration_scaling),
  eef_step_(eef_step), min_fraction_(min_fraction),
  joint_jump_threshold_(joint_jump_threshold), tcp_position_tolerance_(tcp_position_tolerance),
  tcp_orientation_tolerance_rad_(tcp_orientation_tolerance_rad),
  impl_(std::make_unique<Impl>())
{
}

DescendPlannerExecutor::~DescendPlannerExecutor() = default;

PlanResult DescendPlannerExecutor::plan(
  State current_state, State next_state, const ObservationResult & observation)
{
  if (current_state != State::DESCEND || next_state != State::CLOSE_GRIPPER) {
    return planningFailure(FailureCategory::PLANNING, "STATE_NOT_PLANNABLE",
      "DescendPlannerExecutor only supports DESCEND -> CLOSE_GRIPPER");
  }
  if (!observation.snapshot) {
    return planningFailure(FailureCategory::OBSERVATION, "DESCEND_OBSERVATION_MISSING",
      "DESCEND planning requires a current world observation");
  }
  if (!target_policy_) {
    return planningFailure(FailureCategory::CONFIGURATION, "TARGET_POLICY_MISSING",
      "DescendPlannerExecutor requires a target policy");
  }
  const auto target = target_policy_->targetPose(current_state, next_state, observation);
  if (!target.target_pose) {
    return planningFailure(target.failure.value_or(Failure{FailureCategory::CONFIGURATION,
               "TARGET_POLICY_FAILED", "Target policy did not return a DESCEND pose", {}}));
  }
  if (!impl_->move_group) {
    impl_->move_group = std::make_unique<MoveGroupInterface>(node_, planning_group_);
  }
  auto & move_group = *impl_->move_group;
  if (!move_group.startStateMonitor(2.0)) {
    return planningFailure(FailureCategory::OBSERVATION, "STATE_MONITOR_UNAVAILABLE",
      "Failed to start MoveIt current-state monitor");
  }
  if (!move_group.setEndEffectorLink(tcp_link_)) {
    return planningFailure(FailureCategory::CONFIGURATION, "INVALID_TCP_LINK",
      "MoveIt RobotModel does not accept " + tcp_link_);
  }
  const auto current_robot_state = move_group.getCurrentState(2.0);
  if (!current_robot_state) {
    return planningFailure(FailureCategory::OBSERVATION, "CURRENT_STATE_UNAVAILABLE",
      "MoveIt did not provide a current state for Cartesian planning");
  }
  move_group.setPoseReferenceFrame("world");
  move_group.setMaxVelocityScalingFactor(velocity_scaling_);
  move_group.setMaxAccelerationScalingFactor(acceleration_scaling_);
  move_group.setStartState(*current_robot_state);
  logPose(node_->get_logger(), "TARGET_TCP_POSE", *target.target_pose);
  std::vector<geometry_msgs::msg::Pose> waypoints{toGeometryPose(*target.target_pose)};
  moveit_msgs::msg::RobotTrajectory trajectory;
  moveit_msgs::msg::MoveItErrorCodes error_code;
  const auto fraction = move_group.computeCartesianPath(
    waypoints, eef_step_, trajectory, true, &error_code);
  RCLCPP_INFO(node_->get_logger(), "CARTESIAN_FRACTION value=%.6f", fraction);
  if (!trajectory.joint_trajectory.points.empty()) {
    const auto & last_duration = trajectory.joint_trajectory.points.back().time_from_start;
    RCLCPP_INFO(node_->get_logger(), "CARTESIAN_END_TIME sec=%d nanosec=%u",
      last_duration.sec, last_duration.nanosec);
  }
  const auto evidence = makeEvidence(
    trajectory, *current_robot_state, observation.snapshot->tcp_pose_world, tcp_link_, fraction);
  if (!evidence) {
    return planningFailure(FailureCategory::PLAN_VALIDATION,
      "CARTESIAN_TCP_PATH_UNAVAILABLE",
      "Could not reconstruct TCP poses from the Cartesian trajectory");
  }
  const CartesianPlanLimits limits{
    min_fraction_, joint_jump_threshold_, tcp_position_tolerance_,
    tcp_orientation_tolerance_rad_, tcp_position_tolerance_, tcp_orientation_tolerance_rad_};
  const auto validation = validateCartesianPlan(*evidence, *target.target_pose, limits);
  if (!validation.ok) {
    auto failure = validation.failures.front();
    failure.metrics = validation.metrics;
    return planningFailure(std::move(failure));
  }
  logPose(node_->get_logger(), "PLANNED_END_TCP_POSE", evidence->tcp_path.back());
  RCLCPP_INFO(node_->get_logger(), "DESCEND plan succeeded: %zu trajectory points",
    trajectory.joint_trajectory.points.size());
  return {{ActionStatus::SUCCEEDED, std::nullopt},
    std::make_shared<DescendPlanArtifact>(std::move(trajectory))};
}

ActionResult DescendPlannerExecutor::execute(
  State state, std::shared_ptr<const PlanArtifact> plan)
{
  if (state != State::DESCEND) {
    return executionFailure("STATE_NOT_EXECUTABLE",
      "DescendPlannerExecutor only executes DESCEND");
  }
  const auto descend_plan = std::dynamic_pointer_cast<const DescendPlanArtifact>(std::move(plan));
  if (!descend_plan || !impl_->move_group) {
    return executionFailure("INVALID_DESCEND_PLAN_ARTIFACT",
      "DESCEND execution requires a Cartesian trajectory from this planner");
  }
  const bool executed = static_cast<bool>(impl_->move_group->execute(descend_plan->trajectory));
  if (!executed) {
    return executionFailure("MOVEIT_DESCEND_EXECUTION_FAILED",
      "MoveIt failed to execute the Cartesian DESCEND trajectory");
  }
  logPose(node_->get_logger(), "EXECUTED_END_TCP_POSE",
    toPose3d(impl_->move_group->getCurrentPose(tcp_link_).pose));
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ActionResult DescendPlannerExecutor::cancel()
{
  if (impl_->move_group) {
    impl_->move_group->stop();
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

}  // namespace panda_gazebo_demo::pick_place
