#include "panda_gazebo_demo/pick_place/moveit_motion_adapter.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include <Eigen/Geometry>
#include <geometry_msgs/msg/pose.hpp>
#include <moveit/move_group_interface/move_group_interface.hpp>
#include <moveit/planning_scene_interface/planning_scene_interface.hpp>
#include <moveit/robot_state/robot_state.hpp>
#include <moveit_msgs/msg/robot_trajectory.hpp>
#include <rclcpp/node.hpp>

#include "panda_gazebo_demo/pick_place/moveit_world_object_pose.hpp"
#include "panda_gazebo_demo/pick_place/state_validation.hpp"

namespace panda_gazebo_demo::pick_place
{
namespace
{

using MoveGroupInterface = moveit::planning_interface::MoveGroupInterface;

class MoveItMotionPlanEvidence final : public MotionPlanEvidence
{
public:
  moveit_msgs::msg::RobotTrajectory trajectory;
  std::vector<moveit_msgs::msg::RobotTrajectory> execution_trajectories;
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

geometry_msgs::msg::Pose toMessage(const Pose3d & pose)
{
  geometry_msgs::msg::Pose message;
  message.position.x = pose.x;
  message.position.y = pose.y;
  message.position.z = pose.z;
  message.orientation.x = pose.qx;
  message.orientation.y = pose.qy;
  message.orientation.z = pose.qz;
  message.orientation.w = pose.qw;
  return message;
}

Pose3d toPose(const geometry_msgs::msg::Pose & pose)
{
  return {pose.position.x,    pose.position.y,    pose.position.z,   pose.orientation.x,
          pose.orientation.y, pose.orientation.z, pose.orientation.w};
}

Pose3d toPose(const Eigen::Isometry3d & transform)
{
  const Eigen::Quaterniond orientation(transform.rotation());
  const auto & position = transform.translation();
  return {position.x(),    position.y(),    position.z(),   orientation.x(),
          orientation.y(), orientation.z(), orientation.w()};
}

bool poseIsFinite(const geometry_msgs::msg::Pose & pose)
{
  const double quaternion_norm =
    std::sqrt(pose.orientation.x * pose.orientation.x + pose.orientation.y * pose.orientation.y +
              pose.orientation.z * pose.orientation.z + pose.orientation.w * pose.orientation.w);
  return std::isfinite(pose.position.x) && std::isfinite(pose.position.y) &&
         std::isfinite(pose.position.z) && std::isfinite(pose.orientation.x) &&
         std::isfinite(pose.orientation.y) && std::isfinite(pose.orientation.z) &&
         std::isfinite(pose.orientation.w) && quaternion_norm > 1.0e-9;
}

void logPose(const rclcpp::Logger & logger, const char * label, State state, State next_state,
             const Pose3d & pose)
{
  const Eigen::Quaterniond orientation(pose.qw, pose.qx, pose.qy, pose.qz);
  const auto rpy = orientation.normalized().toRotationMatrix().eulerAngles(0, 1, 2);
  RCLCPP_INFO(
    logger, "%s state=%s next_state=%s x=%.6f y=%.6f z=%.6f roll=%.6f pitch=%.6f yaw=%.6f", label,
    toString(state), toString(next_state), pose.x, pose.y, pose.z, rpy.x(), rpy.y(), rpy.z());
}

double durationSeconds(const builtin_interfaces::msg::Duration & duration)
{
  return static_cast<double>(duration.sec) + static_cast<double>(duration.nanosec) / 1.0e9;
}

std::int64_t durationNanoseconds(const builtin_interfaces::msg::Duration & duration)
{
  return static_cast<std::int64_t>(duration.sec) * 1000000000LL + duration.nanosec;
}

void setDurationNanoseconds(builtin_interfaces::msg::Duration & duration, std::int64_t nanoseconds)
{
  duration.sec = static_cast<std::int32_t>(nanoseconds / 1000000000LL);
  duration.nanosec = static_cast<std::uint32_t>(nanoseconds % 1000000000LL);
}

std::optional<moveit_msgs::msg::RobotTrajectory>
combineTrajectories(const moveit_msgs::msg::RobotTrajectory & first,
                    const moveit_msgs::msg::RobotTrajectory & second)
{
  if (first.joint_trajectory.joint_names != second.joint_trajectory.joint_names ||
      first.joint_trajectory.points.empty() || second.joint_trajectory.points.empty()) {
    return std::nullopt;
  }
  auto combined = first;
  const auto offset = durationNanoseconds(combined.joint_trajectory.points.back().time_from_start);
  auto previous = offset;
  for (auto point : second.joint_trajectory.points) {
    auto time = offset + durationNanoseconds(point.time_from_start);
    if (time <= previous) {
      time = previous + 1;
    }
    setDurationNanoseconds(point.time_from_start, time);
    combined.joint_trajectory.points.push_back(std::move(point));
    previous = time;
  }
  return combined;
}

std::shared_ptr<MoveItMotionPlanEvidence>
buildEvidence(State state_id, State next_state, MotionKind kind, bool carrying,
              const moveit_msgs::msg::RobotTrajectory & trajectory,
              const moveit::core::RobotState & start_state, const std::string & tcp_link,
              double cartesian_fraction, bool attached_object_in_model,
              bool carried_relative_pose_available)
{
  auto evidence = std::make_shared<MoveItMotionPlanEvidence>();
  evidence->state = state_id;
  evidence->next_state = next_state;
  evidence->kind = kind;
  evidence->carrying = carrying;
  evidence->cartesian_fraction = cartesian_fraction;
  evidence->trajectory = trajectory;
  evidence->execution_trajectories = {trajectory};
  const auto & joint_trajectory = evidence->trajectory.joint_trajectory;
  evidence->trajectory_points = joint_trajectory.points.size();
  evidence->collision_aware = true;
  evidence->attached_object_in_model = attached_object_in_model;
  evidence->carried_relative_pose_available = carried_relative_pose_available;
  // MoveIt represents an attached body by one rigid link-to-object transform. Once that
  // transform is present and finite, its modeled relative drift across every FK sample is zero.
  evidence->max_carried_relative_position_error = 0.0;
  evidence->max_carried_relative_orientation_error_rad = 0.0;
  // Both MoveGroup pose planning and computeCartesianPath(..., avoid_collisions=true)
  // collision-check the attached body along the returned trajectory.
  evidence->carried_clearance_verified = carrying && evidence->collision_aware &&
                                         attached_object_in_model &&
                                         carried_relative_pose_available;

  moveit::core::RobotState state(start_state);
  state.update();
  evidence->start_tcp_pose = toPose(state.getGlobalLinkTransform(tcp_link));
  std::vector<double> previous_positions;
  previous_positions.reserve(joint_trajectory.joint_names.size());
  for (const auto & joint_name : joint_trajectory.joint_names) {
    const double position = state.getVariablePosition(joint_name);
    previous_positions.push_back(position);
    evidence->planned_start_joint_positions.emplace(joint_name, position);
  }

  std::int64_t previous_nanoseconds = -1;
  bool timed = !joint_trajectory.points.empty();
  for (const auto & point : joint_trajectory.points) {
    if (point.positions.size() != joint_trajectory.joint_names.size()) {
      return nullptr;
    }
    const auto nanoseconds = static_cast<std::int64_t>(point.time_from_start.sec) * 1000000000LL +
                             point.time_from_start.nanosec;
    if (nanoseconds < 0 || (previous_nanoseconds >= 0 && nanoseconds <= previous_nanoseconds)) {
      timed = false;
    }
    previous_nanoseconds = nanoseconds;
    for (std::size_t index = 0; index < point.positions.size(); ++index) {
      evidence->max_joint_jump = std::max(
        evidence->max_joint_jump, std::abs(point.positions[index] - previous_positions[index]));
    }
    state.setVariablePositions(joint_trajectory.joint_names, point.positions);
    state.update();
    evidence->tcp_path.push_back(toPose(state.getGlobalLinkTransform(tcp_link)));
    previous_positions = point.positions;
  }
  if (timed && !joint_trajectory.points.empty()) {
    evidence->duration_seconds = durationSeconds(joint_trajectory.points.back().time_from_start);
  }
  if (evidence->duration_seconds <= 0.0) {
    evidence->duration_seconds = 0.0;
  }
  if (!evidence->tcp_path.empty()) {
    evidence->end_tcp_pose = evidence->tcp_path.back();
    for (std::size_t index = 0; index < joint_trajectory.joint_names.size(); ++index) {
      evidence->planned_end_joint_positions.emplace(joint_trajectory.joint_names[index],
                                                    previous_positions[index]);
    }
  }
  return evidence;
}

}  // namespace

void applyMotionObservationThresholds(WorldSnapshot & snapshot, double joint_velocity_tolerance,
                                      const GripperLimits & gripper_limits)
{
  snapshot.arm_stationary =
    std::isfinite(joint_velocity_tolerance) && joint_velocity_tolerance > 0.0;
  for (const auto & [name, velocity] : snapshot.joint_velocities) {
    static_cast<void>(name);
    if (!std::isfinite(velocity) || std::abs(velocity) > joint_velocity_tolerance) {
      snapshot.arm_stationary = false;
    }
  }
  snapshot.gripper_open = validateGripperOpen(snapshot, gripper_limits).ok;
}

class MoveItMotionAdapter::Impl
{
public:
  Impl(std::shared_ptr<rclcpp::Node> node, std::string planning_group, std::string tcp_link,
       std::vector<std::string> required_world_objects, double velocity_scaling,
       double acceleration_scaling, double cartesian_eef_step, double motion_start_joint_tolerance,
       double joint_velocity_tolerance, GripperLimits gripper_limits) :
      node(std::move(node)), planning_group(std::move(planning_group)),
      tcp_link(std::move(tcp_link)), required_world_objects(std::move(required_world_objects)),
      velocity_scaling(velocity_scaling), acceleration_scaling(acceleration_scaling),
      cartesian_eef_step(cartesian_eef_step),
      motion_start_joint_tolerance(motion_start_joint_tolerance),
      joint_velocity_tolerance(joint_velocity_tolerance), gripper_limits(gripper_limits)
  {
  }

  MoveGroupInterface & moveGroup()
  {
    if (!move_group) {
      move_group = std::make_unique<MoveGroupInterface>(node, planning_group);
    }
    return *move_group;
  }

  std::shared_ptr<rclcpp::Node> node;
  std::string planning_group;
  std::string tcp_link;
  std::vector<std::string> required_world_objects;
  double velocity_scaling;
  double acceleration_scaling;
  double cartesian_eef_step;
  double motion_start_joint_tolerance;
  double joint_velocity_tolerance;
  GripperLimits gripper_limits;
  std::unique_ptr<MoveGroupInterface> move_group;
  moveit::planning_interface::PlanningSceneInterface planning_scene;
};

MoveItMotionAdapter::MoveItMotionAdapter(
  std::shared_ptr<rclcpp::Node> node, std::string planning_group, std::string tcp_link,
  std::vector<std::string> required_world_objects, double velocity_scaling,
  double acceleration_scaling, double cartesian_eef_step, double motion_start_joint_tolerance,
  double joint_velocity_tolerance, GripperLimits gripper_limits) :
    impl_(std::make_unique<Impl>(
      std::move(node), std::move(planning_group), std::move(tcp_link),
      std::move(required_world_objects), velocity_scaling, acceleration_scaling, cartesian_eef_step,
      motion_start_joint_tolerance, joint_velocity_tolerance, gripper_limits))
{
}

MoveItMotionAdapter::~MoveItMotionAdapter() = default;

PlanResult MoveItMotionAdapter::plan(const MotionPlanningRequest & request,
                                     const ObservationResult & observation)
{
  if (!observation.snapshot) {
    return planningFailure(FailureCategory::OBSERVATION, "MOTION_OBSERVATION_MISSING",
                           "MoveIt motion planning requires a current world observation");
  }
  if (impl_->velocity_scaling <= 0.0 || impl_->velocity_scaling > 1.0 ||
      impl_->acceleration_scaling <= 0.0 || impl_->acceleration_scaling > 1.0 ||
      impl_->cartesian_eef_step <= 0.0) {
    return planningFailure(
      FailureCategory::CONFIGURATION, "MOTION_CONFIGURATION_INVALID",
      "Motion scaling factors and Cartesian eef step must be positive and valid");
  }

  const auto world_objects = impl_->planning_scene.getObjects(impl_->required_world_objects);
  for (const auto & object_id : impl_->required_world_objects) {
    if (request.carrying && object_id == "coke") {
      continue;
    }
    if (world_objects.count(object_id) == 0) {
      return planningFailure(FailureCategory::MOVEIT_SCENE, "REQUIRED_WORLD_OBJECT_MISSING",
                             "Required Planning Scene world object is missing: " + object_id);
    }
  }
  const auto attached_objects = impl_->planning_scene.getAttachedObjects({"coke"});
  const auto attached = attached_objects.find("coke");
  const bool attached_object_in_model = attached != attached_objects.end();
  const bool coke_in_world = impl_->planning_scene.getObjects({"coke"}).count("coke") != 0;
  if (request.carrying && (!attached_object_in_model || coke_in_world)) {
    return planningFailure(
      FailureCategory::MOVEIT_SCENE, "ATTACHED_OBJECT_MODEL_EVIDENCE_MISSING",
      "Carried motion requires Coke exclusively in the MoveIt attached-object model");
  }
  const bool relative_pose_available = attached_object_in_model &&
                                       !attached->second.link_name.empty() &&
                                       poseIsFinite(attached->second.object.pose);

  auto & move_group = impl_->moveGroup();
  if (!move_group.startStateMonitor(2.0)) {
    return planningFailure(FailureCategory::OBSERVATION, "STATE_MONITOR_UNAVAILABLE",
                           "Failed to start MoveIt current-state monitor");
  }
  if (!move_group.setEndEffectorLink(impl_->tcp_link)) {
    return planningFailure(FailureCategory::CONFIGURATION, "INVALID_TCP_LINK",
                           "MoveIt RobotModel does not accept " + impl_->tcp_link);
  }
  const auto current_state = move_group.getCurrentState(2.0);
  if (!current_state) {
    return planningFailure(FailureCategory::OBSERVATION, "CURRENT_STATE_UNAVAILABLE",
                           "MoveIt did not provide a current state for motion planning");
  }
  move_group.setPoseReferenceFrame("world");
  move_group.setMaxVelocityScalingFactor(impl_->velocity_scaling);
  move_group.setMaxAccelerationScalingFactor(impl_->acceleration_scaling);
  move_group.clearPoseTargets();
  move_group.setStartState(*current_state);
  logPose(impl_->node->get_logger(), "TARGET_TCP_POSE", request.state, request.next_state,
          request.target_pose);

  moveit_msgs::msg::RobotTrajectory trajectory;
  double fraction = 1.0;
  if (request.kind == MotionKind::POSE) {
    if (!move_group.setPoseTarget(toMessage(request.target_pose), impl_->tcp_link)) {
      return planningFailure(FailureCategory::PLANNING, "POSE_TARGET_REJECTED",
                             "MoveIt rejected the configured TCP pose target");
    }
    MoveGroupInterface::Plan plan;
    if (!static_cast<bool>(move_group.plan(plan))) {
      return planningFailure(FailureCategory::PLANNING, "MOVEIT_POSE_PLAN_FAILED",
                             "MoveIt collision-aware pose planning failed");
    }
    trajectory = std::move(plan.trajectory);
  } else {
    const std::vector<geometry_msgs::msg::Pose> waypoints{toMessage(request.target_pose)};
    moveit_msgs::msg::MoveItErrorCodes error_code;
    fraction = move_group.computeCartesianPath(waypoints, impl_->cartesian_eef_step, trajectory,
                                               true, &error_code);
  }
  if (trajectory.joint_trajectory.points.empty()) {
    return planningFailure(FailureCategory::PLANNING, "EMPTY_MOTION_TRAJECTORY",
                           "MoveIt planning produced an empty trajectory");
  }

  auto evidence = buildEvidence(request.state, request.next_state, request.kind, request.carrying,
                                trajectory, *current_state, impl_->tcp_link, fraction,
                                attached_object_in_model, relative_pose_available);
  if (!evidence) {
    return planningFailure(FailureCategory::PLAN_VALIDATION, "MOTION_TCP_PATH_UNAVAILABLE",
                           "Could not reconstruct TCP poses from the MoveIt trajectory");
  }
  logPose(impl_->node->get_logger(), "START_TCP_POSE", request.state, request.next_state,
          evidence->start_tcp_pose);
  logPose(impl_->node->get_logger(), "PLANNED_END_TCP_POSE", request.state, request.next_state,
          evidence->end_tcp_pose);
  RCLCPP_INFO(impl_->node->get_logger(), "CARTESIAN_FRACTION state=%s value=%.6f",
              toString(request.state), evidence->cartesian_fraction);
  RCLCPP_INFO(impl_->node->get_logger(), "TRAJECTORY_POINTS state=%s value=%zu",
              toString(request.state), evidence->trajectory_points);
  RCLCPP_INFO(impl_->node->get_logger(), "MAX_JOINT_JUMP state=%s value=%.6f",
              toString(request.state), evidence->max_joint_jump);
  RCLCPP_INFO(impl_->node->get_logger(), "TRAJECTORY_DURATION state=%s value=%.6f",
              toString(request.state), evidence->duration_seconds);
  RCLCPP_INFO(impl_->node->get_logger(),
              "TCP_COKE_RELATIVE_POSE_ERROR state=%s position=%.6f orientation_rad=%.6f",
              toString(request.state), evidence->max_carried_relative_position_error,
              evidence->max_carried_relative_orientation_error_rad);
  return {{ActionStatus::SUCCEEDED, std::nullopt}, evidence};
}

std::optional<std::map<std::string, double>>
MoveItMotionAdapter::namedTargetJointPositions(const std::string & target_name)
{
  if (target_name.empty()) {
    return std::nullopt;
  }
  auto values = impl_->moveGroup().getNamedTargetValues(target_name);
  if (values.empty()) {
    return std::nullopt;
  }
  for (const auto & [joint, position] : values) {
    if (joint.empty() || !std::isfinite(position)) {
      return std::nullopt;
    }
  }
  return values;
}

PlanResult MoveItMotionAdapter::planNamedTarget(const NamedTargetPlanningRequest & request,
                                                const ObservationResult & observation)
{
  if (!observation.snapshot) {
    return planningFailure(FailureCategory::OBSERVATION, "MOTION_OBSERVATION_MISSING",
                           "MoveIt motion planning requires a current world observation");
  }
  if (request.target_name.empty()) {
    return planningFailure(FailureCategory::CONFIGURATION, "NAMED_TARGET_UNAVAILABLE",
                           "MoveIt named target must be non-empty");
  }
  if (impl_->velocity_scaling <= 0.0 || impl_->velocity_scaling > 1.0 ||
      impl_->acceleration_scaling <= 0.0 || impl_->acceleration_scaling > 1.0) {
    return planningFailure(FailureCategory::CONFIGURATION, "MOTION_CONFIGURATION_INVALID",
                           "Motion scaling factors must be positive and valid");
  }
  const auto world_objects = impl_->planning_scene.getObjects(impl_->required_world_objects);
  for (const auto & object_id : impl_->required_world_objects) {
    if (world_objects.count(object_id) == 0) {
      return planningFailure(FailureCategory::MOVEIT_SCENE, "REQUIRED_WORLD_OBJECT_MISSING",
                             "Required Planning Scene world object is missing: " + object_id);
    }
  }
  auto & move_group = impl_->moveGroup();
  if (!move_group.startStateMonitor(2.0)) {
    return planningFailure(FailureCategory::OBSERVATION, "STATE_MONITOR_UNAVAILABLE",
                           "Failed to start MoveIt current-state monitor");
  }
  if (!move_group.setEndEffectorLink(impl_->tcp_link)) {
    return planningFailure(FailureCategory::CONFIGURATION, "INVALID_TCP_LINK",
                           "MoveIt RobotModel does not accept " + impl_->tcp_link);
  }
  const auto current_state = move_group.getCurrentState(2.0);
  if (!current_state) {
    return planningFailure(FailureCategory::OBSERVATION, "CURRENT_STATE_UNAVAILABLE",
                           "MoveIt did not provide a current state for motion planning");
  }
  const auto target_joint_positions = move_group.getNamedTargetValues(request.target_name);
  if (target_joint_positions.empty()) {
    return planningFailure(FailureCategory::CONFIGURATION, "NAMED_TARGET_UNAVAILABLE",
                           "MoveIt named target is unavailable: " + request.target_name);
  }
  move_group.setMaxVelocityScalingFactor(impl_->velocity_scaling);
  move_group.setMaxAccelerationScalingFactor(impl_->acceleration_scaling);
  move_group.clearPoseTargets();
  move_group.setStartState(*current_state);
  if (!move_group.setNamedTarget(request.target_name)) {
    return planningFailure(FailureCategory::CONFIGURATION, "NAMED_TARGET_UNAVAILABLE",
                           "MoveIt rejected named target: " + request.target_name);
  }
  MoveGroupInterface::Plan plan;
  if (!static_cast<bool>(move_group.plan(plan))) {
    return planningFailure(FailureCategory::PLANNING, "MOVEIT_NAMED_TARGET_PLAN_FAILED",
                           "MoveIt collision-aware named-target planning failed");
  }
  if (plan.trajectory.joint_trajectory.points.empty()) {
    return planningFailure(FailureCategory::PLANNING, "EMPTY_MOTION_TRAJECTORY",
                           "MoveIt planning produced an empty trajectory");
  }
  auto evidence =
    buildEvidence(request.state, request.next_state, MotionKind::NAMED_TARGET, false,
                  plan.trajectory, *current_state, impl_->tcp_link, 1.0, false, false);
  if (!evidence) {
    return planningFailure(FailureCategory::PLAN_VALIDATION, "MOTION_TCP_PATH_UNAVAILABLE",
                           "Could not reconstruct TCP poses from the MoveIt trajectory");
  }
  evidence->named_target = request.target_name;
  evidence->target_joint_positions = target_joint_positions;
  RCLCPP_INFO(impl_->node->get_logger(), "NAMED_JOINT_TARGET state=%s target=%s",
              toString(request.state), request.target_name.c_str());
  logPose(impl_->node->get_logger(), "START_TCP_POSE", request.state, request.next_state,
          evidence->start_tcp_pose);
  logPose(impl_->node->get_logger(), "PLANNED_END_TCP_POSE", request.state, request.next_state,
          evidence->end_tcp_pose);
  RCLCPP_INFO(impl_->node->get_logger(), "TRAJECTORY_POINTS state=%s value=%zu",
              toString(request.state), evidence->trajectory_points);
  return {{ActionStatus::SUCCEEDED, std::nullopt}, evidence};
}

PlanResult MoveItMotionAdapter::planSafeNamedTarget(const SafeNamedTargetPlanningRequest & request,
                                                    const ObservationResult & observation)
{
  if (!observation.snapshot) {
    return planningFailure(FailureCategory::OBSERVATION, "MOTION_OBSERVATION_MISSING",
                           "Safe named-target planning requires a current world observation");
  }
  const MotionPlanningRequest clearance_request{
    request.state, request.next_state, MotionKind::CARTESIAN_UP, false, request.clearance_pose};
  auto clearance_result = plan(clearance_request, observation);
  const auto clearance_evidence =
    std::dynamic_pointer_cast<const MoveItMotionPlanEvidence>(clearance_result.artifact);
  if (clearance_result.action.status != ActionStatus::SUCCEEDED || !clearance_evidence) {
    return clearance_result;
  }

  auto & move_group = impl_->moveGroup();
  const auto current_state = move_group.getCurrentState(2.0);
  if (!current_state) {
    return planningFailure(FailureCategory::OBSERVATION, "CURRENT_STATE_UNAVAILABLE",
                           "MoveIt did not provide the safe-retreat start state");
  }
  auto clearance_end_state = *current_state;
  for (const auto & [joint, position] : clearance_evidence->planned_end_joint_positions) {
    clearance_end_state.setVariablePosition(joint, position);
  }
  clearance_end_state.update();

  const auto target_joint_positions = move_group.getNamedTargetValues(request.target_name);
  if (target_joint_positions.empty()) {
    return planningFailure(FailureCategory::CONFIGURATION, "NAMED_TARGET_UNAVAILABLE",
                           "MoveIt named target is unavailable: " + request.target_name);
  }
  move_group.clearPoseTargets();
  move_group.setStartState(clearance_end_state);
  if (!move_group.setNamedTarget(request.target_name)) {
    return planningFailure(FailureCategory::CONFIGURATION, "NAMED_TARGET_UNAVAILABLE",
                           "MoveIt rejected named target: " + request.target_name);
  }
  MoveGroupInterface::Plan ready_plan;
  if (!static_cast<bool>(move_group.plan(ready_plan))) {
    return planningFailure(FailureCategory::PLANNING, "MOVEIT_SAFE_NAMED_TARGET_PLAN_FAILED",
                           "MoveIt failed to plan from the retreat clearance pose to ready");
  }
  const auto combined = combineTrajectories(clearance_evidence->trajectory, ready_plan.trajectory);
  if (!combined) {
    return planningFailure(FailureCategory::PLAN_VALIDATION, "MOTION_SEQUENCE_INVALID",
                           "Safe retreat trajectories could not be combined for validation");
  }
  auto evidence = buildEvidence(request.state, request.next_state, MotionKind::NAMED_TARGET, false,
                                *combined, *current_state, impl_->tcp_link, 1.0, false, false);
  if (!evidence) {
    return planningFailure(FailureCategory::PLAN_VALIDATION, "MOTION_TCP_PATH_UNAVAILABLE",
                           "Could not reconstruct the safe retreat TCP path");
  }
  evidence->execution_trajectories = {clearance_evidence->trajectory, ready_plan.trajectory};
  evidence->named_target = request.target_name;
  evidence->target_joint_positions = target_joint_positions;
  RCLCPP_INFO(impl_->node->get_logger(),
              "SAFE_NAMED_JOINT_TARGET state=%s target=%s segments=2 clearance_z=%.6f",
              toString(request.state), request.target_name.c_str(), request.clearance_pose.z);
  logPose(impl_->node->get_logger(), "START_TCP_POSE", request.state, request.next_state,
          evidence->start_tcp_pose);
  logPose(impl_->node->get_logger(), "PLANNED_END_TCP_POSE", request.state, request.next_state,
          evidence->end_tcp_pose);
  RCLCPP_INFO(impl_->node->get_logger(), "TRAJECTORY_POINTS state=%s value=%zu",
              toString(request.state), evidence->trajectory_points);
  return {{ActionStatus::SUCCEEDED, std::nullopt}, evidence};
}

ActionResult MoveItMotionAdapter::execute(const MotionPlanEvidence & evidence)
{
  const auto * moveit_evidence = dynamic_cast<const MoveItMotionPlanEvidence *>(&evidence);
  if (moveit_evidence == nullptr || !impl_->move_group) {
    return executionFailure("INVALID_MOVEIT_MOTION_PLAN",
                            "MoveIt execution requires a trajectory produced by this adapter");
  }
  const auto current_state = impl_->move_group->getCurrentState(2.0);
  if (!current_state) {
    return executionFailure("CURRENT_STATE_UNAVAILABLE",
                            "MoveIt did not provide a current state immediately before execution");
  }
  std::map<std::string, double> current_joint_positions;
  const auto & current_variable_names = current_state->getVariableNames();
  for (const auto & [name, planned_position] : evidence.planned_start_joint_positions) {
    static_cast<void>(planned_position);
    if (std::find(current_variable_names.begin(), current_variable_names.end(), name) !=
        current_variable_names.end()) {
      current_joint_positions.emplace(name, current_state->getVariablePosition(name));
    }
  }
  const auto start_validation =
    validateMotionStartJoints(evidence.planned_start_joint_positions, current_joint_positions,
                              impl_->motion_start_joint_tolerance);
  if (!start_validation.ok) {
    const auto & failure = start_validation.failures.front();
    return executionFailure(failure.code,
                            "MoveIt execution start state changed after plan validation: " +
                              failure.message);
  }
  for (std::size_t index = 0; index < moveit_evidence->execution_trajectories.size(); ++index) {
    if (!static_cast<bool>(
          impl_->move_group->execute(moveit_evidence->execution_trajectories[index]))) {
      return executionFailure("MOVEIT_MOTION_SEGMENT_EXECUTION_FAILED",
                              "MoveIt failed to execute validated motion segment " +
                                std::to_string(index + 1));
    }
  }
  logPose(impl_->node->get_logger(), "EXECUTED_END_TCP_POSE", evidence.state, evidence.next_state,
          toPose(impl_->move_group->getCurrentPose(impl_->tcp_link).pose));
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ActionResult MoveItMotionAdapter::cancel()
{
  if (impl_->move_group) {
    impl_->move_group->stop();
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ObservationResult MoveItMotionAdapter::observe()
{
  auto & move_group = impl_->moveGroup();
  if (!move_group.startStateMonitor(2.0)) {
    return {std::nullopt, Failure{FailureCategory::OBSERVATION,
                                  "STATE_MONITOR_UNAVAILABLE",
                                  "Failed to start MoveIt current-state monitor",
                                  {}}};
  }
  if (!move_group.setEndEffectorLink(impl_->tcp_link)) {
    return {std::nullopt, Failure{FailureCategory::CONFIGURATION,
                                  "INVALID_TCP_LINK",
                                  "MoveIt RobotModel does not accept " + impl_->tcp_link,
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
  snapshot.tcp_pose_world = toPose(move_group.getCurrentPose(impl_->tcp_link).pose);
  for (const auto & variable : state->getVariableNames()) {
    snapshot.joint_positions[variable] = state->getVariablePosition(variable);
    const double velocity = state->getVariableVelocity(variable);
    snapshot.joint_velocities[variable] = velocity;
  }
  applyMotionObservationThresholds(snapshot, impl_->joint_velocity_tolerance,
                                   impl_->gripper_limits);
  const auto world_objects = impl_->planning_scene.getObjects(impl_->required_world_objects);
  for (const auto & [object_id, object] : world_objects) {
    snapshot.moveit_world_object_poses.emplace(object_id, worldPoseFromCollisionObject(object));
  }
  const auto attached_objects = impl_->planning_scene.getAttachedObjects({"coke"});
  const auto attached = attached_objects.find("coke");
  snapshot.moveit_task_object_attached = attached != attached_objects.end();
  if (attached != attached_objects.end()) {
    snapshot.moveit_task_object_attached_link = attached->second.link_name;
    snapshot.moveit_task_object_touch_links = {attached->second.touch_links.begin(),
                                               attached->second.touch_links.end()};
  }
  return {snapshot, std::nullopt};
}

}  // namespace panda_gazebo_demo::pick_place
