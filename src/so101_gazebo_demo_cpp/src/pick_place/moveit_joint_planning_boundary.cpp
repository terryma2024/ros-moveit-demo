#include "so101_gazebo_demo/pick_place/moveit_joint_planning_boundary.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <cstdint>
#include <future>
#include <limits>
#include <map>
#include <mutex>
#include <set>
#include <thread>
#include <utility>

#include <Eigen/Dense>
#include <Eigen/Geometry>
#include <moveit/move_group_interface/move_group_interface.hpp>
#include <moveit/kinematic_constraints/utils.hpp>
#include <moveit/planning_scene/planning_scene.hpp>
#include <moveit/planning_scene_interface/planning_scene_interface.hpp>
#include <moveit/robot_state/robot_state.hpp>
#include <moveit/robot_state/conversions.hpp>
#include <moveit_msgs/action/move_group.hpp>
#include <moveit_msgs/msg/move_it_error_codes.hpp>
#include <action_msgs/srv/cancel_goal.hpp>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <sensor_msgs/msg/joint_state.hpp>

namespace so101_gazebo_demo::pick_place
{

std::set<std::string> exactTaskObjectTouchWhitelist(const SO101Profile & profile)
{
  std::set<std::string> result;
  for (const auto & link : profile.moveit_touch_links) {
    result.insert(profile.task_object_id + ":" + link);
  }
  return result;
}

namespace
{

Pose3d poseFrom(const Eigen::Isometry3d & transform)
{
  const Eigen::Quaterniond q(transform.rotation());
  const auto & p = transform.translation();
  return {p.x(), p.y(), p.z(), q.x(), q.y(), q.z(), q.w()};
}

Pose3d poseFrom(const geometry_msgs::msg::Pose & pose)
{
  return {pose.position.x,    pose.position.y,    pose.position.z,   pose.orientation.x,
          pose.orientation.y, pose.orientation.z, pose.orientation.w};
}

double distance(const Pose3d & pose, const Vec3 & target)
{
  const double dx = pose.x - target.x;
  const double dy = pose.y - target.y;
  const double dz = pose.z - target.z;
  return std::sqrt(dx * dx + dy * dy + dz * dz);
}

Eigen::Vector3d rotatedAxis(const Pose3d & pose, const Vec3 & local)
{
  Eigen::Quaterniond q(pose.qw, pose.qx, pose.qy, pose.qz);
  Eigen::Vector3d axis(local.x, local.y, local.z);
  if (q.norm() <= 1e-12 || axis.norm() <= 1e-12) {
    return Eigen::Vector3d::Constant(std::numeric_limits<double>::quiet_NaN());
  }
  return q.normalized() * axis.normalized();
}

double durationSeconds(const builtin_interfaces::msg::Duration & duration)
{
  return static_cast<double>(duration.sec) + static_cast<double>(duration.nanosec) * 1e-9;
}

double halton(std::size_t index, unsigned base)
{
  double result = 0.0;
  double fraction = 1.0;
  while (index > 0) {
    fraction /= static_cast<double>(base);
    result += fraction * static_cast<double>(index % base);
    index /= base;
  }
  return result;
}

JointSegmentPlanResult planFail(FailureCategory category, std::string code, std::string message)
{
  return {{ActionStatus::FAILED, Failure{category, std::move(code), std::move(message), {}}},
          std::nullopt};
}

std::string policyPair(const SO101Profile & profile, std::string first, std::string second)
{
  if (second == profile.task_object_id)
    std::swap(first, second);
  if (first == profile.task_object_id)
    return first + ":" + second;
  if (second < first)
    std::swap(first, second);
  return first + ":" + second;
}

bool validTouchWhitelist(const std::set<std::string> & requested, const SO101Profile & profile)
{
  return requested.empty() || requested == exactTaskObjectTouchWhitelist(profile);
}

bool validTemporalContact(const std::optional<TemporalContactPolicy> & requested,
                          const SO101Profile & profile)
{
  if (!requested)
    return true;
  const auto support =
    std::set<std::string>{policyPair(profile, profile.task_object_id, profile.table_object)};
  const auto gripper = exactTaskObjectTouchWhitelist(profile);
  if (requested->location == TemporalContactLocation::FIRST_ONLY) {
    return requested->max_axial_clearance_m == 0.0 &&
           (requested->allowed_pairs == support || requested->allowed_pairs == gripper);
  }
  if (requested->location == TemporalContactLocation::LAST_ONLY) {
    return requested->max_axial_clearance_m == 0.0 && requested->allowed_pairs == support;
  }
  return requested->location == TemporalContactLocation::PREFIX_UNTIL_AXIAL_CLEARANCE &&
         (requested->allowed_pairs == support || requested->allowed_pairs == gripper) &&
         std::isfinite(requested->max_axial_clearance_m) && requested->max_axial_clearance_m > 0.0;
}

}  // namespace

std::optional<Pose3d> updatedLinkPose(const moveit::core::RobotState & source,
                                      const std::string & link_name)
{
  if (!source.getRobotModel()->hasLinkModel(link_name))
    return std::nullopt;
  moveit::core::RobotState current(source);
  current.update();
  return poseFrom(current.getGlobalLinkTransform(link_name));
}

std::optional<Pose3d> updatedAttachedBodyPose(const moveit::core::RobotState & source,
                                              const std::string & attached_body_name)
{
  moveit::core::RobotState current(source);
  current.update();
  if (!current.hasAttachedBody(attached_body_name))
    return std::nullopt;
  const auto * attached = current.getAttachedBody(attached_body_name);
  if (!attached)
    return std::nullopt;
  return poseFrom(attached->getGlobalPose());
}

std::optional<moveit_msgs::msg::RobotTrajectory>
executableTrajectoryFromValidatedArtifact(const MotionPlanArtifact & artifact,
                                          const std::vector<std::string> & expected_joint_names)
{
  if (!artifact.moveit_success || !artifact.collision_aware || !artifact.time_parameterized ||
      expected_joint_names.empty() || artifact.joint_names != expected_joint_names ||
      artifact.trajectory_points < 2 || artifact.samples.size() != artifact.trajectory_points ||
      artifact.start_joint_positions.size() != expected_joint_names.size() ||
      artifact.goal_joint_positions.size() != expected_joint_names.size()) {
    return std::nullopt;
  }
  moveit_msgs::msg::RobotTrajectory trajectory;
  trajectory.joint_trajectory.joint_names = artifact.joint_names;
  double previous_time = -1.0;
  for (const auto & sample : artifact.samples) {
    if (sample.joint_positions.size() != expected_joint_names.size() ||
        !std::isfinite(sample.time_from_start_seconds) || sample.time_from_start_seconds < 0.0 ||
        (previous_time >= 0.0 && sample.time_from_start_seconds <= previous_time)) {
      return std::nullopt;
    }
    trajectory_msgs::msg::JointTrajectoryPoint point;
    for (const double position : sample.joint_positions) {
      if (!std::isfinite(position))
        return std::nullopt;
      point.positions.push_back(position);
    }
    const auto nanoseconds = std::chrono::duration_cast<std::chrono::nanoseconds>(
      std::chrono::duration<double>(sample.time_from_start_seconds));
    point.time_from_start.sec = static_cast<std::int32_t>(nanoseconds.count() / 1000000000LL);
    point.time_from_start.nanosec = static_cast<std::uint32_t>(nanoseconds.count() % 1000000000LL);
    trajectory.joint_trajectory.points.push_back(std::move(point));
    previous_time = sample.time_from_start_seconds;
  }
  const auto same = [](const std::vector<double> & first, const std::vector<double> & second) {
    if (first.size() != second.size())
      return false;
    for (std::size_t i = 0; i < first.size(); ++i) {
      if (!std::isfinite(first[i]) || !std::isfinite(second[i]) ||
          std::abs(first[i] - second[i]) > 1e-9)
        return false;
    }
    return true;
  };
  if (!same(trajectory.joint_trajectory.points.front().positions, artifact.start_joint_positions) ||
      !same(trajectory.joint_trajectory.points.back().positions, artifact.goal_joint_positions)) {
    return std::nullopt;
  }
  return trajectory;
}

std::optional<CurrentJointStateEvidence>
currentJointStateEvidenceFromMessage(const sensor_msgs::msg::JointState & message,
                                     const SO101Profile & profile,
                                     std::chrono::steady_clock::time_point received_at)
{
  if (received_at == std::chrono::steady_clock::time_point{} || message.name.empty() ||
      message.position.size() != message.name.size() ||
      message.velocity.size() != message.name.size() || message.header.stamp.sec < 0) {
    return std::nullopt;
  }
  CurrentJointStateEvidence result;
  result.joint_names = profile.arm_joints;
  result.received_at = received_at;
  result.observed_stamp_nanoseconds =
    static_cast<std::uint64_t>(message.header.stamp.sec) * 1000000000ULL +
    static_cast<std::uint64_t>(message.header.stamp.nanosec);
  auto append = [&](const std::string & required, bool gripper) {
    const auto first = std::find(message.name.begin(), message.name.end(), required);
    if (first == message.name.end() ||
        std::find(std::next(first), message.name.end(), required) != message.name.end()) {
      return false;
    }
    const auto index = static_cast<std::size_t>(std::distance(message.name.begin(), first));
    if (!std::isfinite(message.position[index]) || !std::isfinite(message.velocity[index])) {
      return false;
    }
    if (gripper) {
      result.gripper_position = message.position[index];
      result.gripper_velocity = message.velocity[index];
    } else {
      result.positions.push_back(message.position[index]);
      result.velocities.push_back(message.velocity[index]);
    }
    return true;
  };
  for (const auto & name : profile.arm_joints) {
    if (!append(name, false))
      return std::nullopt;
  }
  if (!append(profile.gripper_joint, true))
    return std::nullopt;
  return result;
}

ActionResult cancelRequestScopedGoalAndWait(IRequestScopedGoalCancellation & goal,
                                            double cancel_ack_timeout_seconds,
                                            double terminal_timeout_seconds)
{
  auto cancel = goal.requestCancel(cancel_ack_timeout_seconds);
  if (cancel.status != ActionStatus::SUCCEEDED)
    return cancel;
  if (!goal.waitForTerminal(terminal_timeout_seconds)) {
    return {ActionStatus::TIMED_OUT,
            Failure{FailureCategory::PLANNING,
                    "MOVE_GROUP_CANCEL_TERMINAL_TIMEOUT",
                    "MoveGroup goal did not reach a terminal state after cancellation",
                    {}}};
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ActionResult classifyMicroLiftPlanningOutcome(const MicroLiftPlanningOutcome & outcome)
{
  if (!outcome.failure_stage) {
    if (outcome.result &&
        outcome.result->error_code.val == moveit_msgs::msg::MoveItErrorCodes::SUCCESS &&
        !outcome.result->planned_trajectory.joint_trajectory.points.empty()) {
      return {ActionStatus::SUCCEEDED, std::nullopt};
    }
    return {ActionStatus::FAILED,
            Failure{FailureCategory::PLANNING,
                    "MICRO_LIFT_MOVEIT_PLAN_FAILED",
                    "MoveIt could not produce a request-scoped touch-aware world-Z micro-lift plan",
                    {}}};
  }
  switch (*outcome.failure_stage) {
    case PlanningFailureStage::GOAL_ACCEPT_TIMEOUT:
      return {ActionStatus::FAILED,
              Failure{FailureCategory::PLANNING,
                      "MICRO_LIFT_MOVE_GROUP_GOAL_TIMEOUT",
                      "MoveGroup did not accept the request-scoped micro-lift goal in time",
                      {}}};
    case PlanningFailureStage::GOAL_REJECTED:
      return {ActionStatus::FAILED, Failure{FailureCategory::PLANNING,
                                            "MICRO_LIFT_MOVE_GROUP_GOAL_REJECTED",
                                            "MoveGroup rejected the request-scoped micro-lift goal",
                                            {}}};
    case PlanningFailureStage::RESULT_TIMEOUT:
      if (outcome.action.status != ActionStatus::SUCCEEDED && outcome.action.failure)
        return outcome.action;
      return {ActionStatus::FAILED,
              Failure{FailureCategory::PLANNING,
                      "MICRO_LIFT_MOVE_GROUP_RESULT_TIMEOUT",
                      "Request-scoped micro-lift planning did not finish in time",
                      {}}};
    case PlanningFailureStage::TRANSPORT_FAILURE:
    case PlanningFailureStage::MISSING_RESULT:
    case PlanningFailureStage::MOVEIT_ERROR:
    case PlanningFailureStage::EMPTY_TRAJECTORY:
      return {
        ActionStatus::FAILED,
        Failure{FailureCategory::PLANNING,
                "MICRO_LIFT_MOVEIT_PLAN_FAILED",
                "MoveIt could not produce a request-scoped touch-aware world-Z micro-lift plan",
                {}}};
  }
  return {ActionStatus::FAILED, Failure{FailureCategory::INTERNAL,
                                        "MICRO_LIFT_OUTCOME_INVALID",
                                        "Micro-lift planning outcome was not classifiable",
                                        {}}};
}

namespace
{

using MoveGroupGoalHandle = rclcpp_action::ClientGoalHandle<moveit_msgs::action::MoveGroup>;

class RosMoveGroupGoalCancellation final : public IRequestScopedGoalCancellation
{
public:
  RosMoveGroupGoalCancellation(
    rclcpp_action::Client<moveit_msgs::action::MoveGroup>::SharedPtr client,
    MoveGroupGoalHandle::SharedPtr goal_handle,
    std::shared_future<MoveGroupGoalHandle::WrappedResult> result_future) :
      client_(std::move(client)), goal_handle_(std::move(goal_handle)),
      result_future_(std::move(result_future))
  {
  }

  ActionResult requestCancel(double timeout_seconds) override
  {
    const auto future = client_->async_cancel_goal(goal_handle_);
    if (future.wait_for(std::chrono::duration<double>(timeout_seconds)) !=
        std::future_status::ready) {
      cancel_acknowledged_ = false;
      return {ActionStatus::TIMED_OUT, Failure{FailureCategory::PLANNING,
                                               "MOVE_GROUP_CANCEL_ACK_TIMEOUT",
                                               "MoveGroup did not acknowledge cancellation in time",
                                               {}}};
    }
    const auto & response = future.get();
    if (!response || response->return_code != action_msgs::srv::CancelGoal::Response::ERROR_NONE ||
        response->goals_canceling.empty()) {
      cancel_acknowledged_ = false;
      return {ActionStatus::FAILED,
              Failure{FailureCategory::PLANNING,
                      "MOVE_GROUP_CANCEL_REJECTED",
                      "MoveGroup rejected cancellation of the timed-out planning goal",
                      {}}};
    }
    cancel_acknowledged_ = true;
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }

  std::optional<RequestScopedGoalTerminal> waitForTerminal(double timeout_seconds) override
  {
    if (result_future_.wait_for(std::chrono::duration<double>(timeout_seconds)) !=
        std::future_status::ready) {
      return std::nullopt;
    }
    switch (result_future_.get().code) {
      case rclcpp_action::ResultCode::SUCCEEDED:
        terminal_ = RequestScopedGoalTerminal::SUCCEEDED;
        return terminal_;
      case rclcpp_action::ResultCode::ABORTED:
        terminal_ = RequestScopedGoalTerminal::ABORTED;
        return terminal_;
      case rclcpp_action::ResultCode::CANCELED:
        terminal_ = RequestScopedGoalTerminal::CANCELED;
        return terminal_;
      default:
        return std::nullopt;
    }
  }

  [[nodiscard]] std::optional<bool> cancelAcknowledged() const
  {
    return cancel_acknowledged_;
  }

  [[nodiscard]] std::optional<RequestScopedGoalTerminal> terminal() const
  {
    return terminal_;
  }

private:
  rclcpp_action::Client<moveit_msgs::action::MoveGroup>::SharedPtr client_;
  MoveGroupGoalHandle::SharedPtr goal_handle_;
  std::shared_future<MoveGroupGoalHandle::WrappedResult> result_future_;
  std::optional<bool> cancel_acknowledged_;
  std::optional<RequestScopedGoalTerminal> terminal_;
};

}  // namespace

class MoveItJointPlanningBoundary::Impl
{
public:
  Impl(std::shared_ptr<rclcpp::Node> node, SO101Profile profile,
       MoveItJointPlanningBoundaryOptions options) :
      node(std::move(node)), profile(std::move(profile)), planner_id(std::move(options.planner_id)),
      velocity_scaling(options.velocity_scaling),
      acceleration_scaling(options.acceleration_scaling),
      state_timeout_seconds(options.state_timeout_seconds),
      diagnostics(std::move(options.diagnostics))
  {
    joint_state_subscription = this->node->create_subscription<sensor_msgs::msg::JointState>(
      "/joint_states", rclcpp::SensorDataQoS(),
      [this](const sensor_msgs::msg::JointState::ConstSharedPtr & message) {
        auto evidence = currentJointStateEvidenceFromMessage(*message, this->profile,
                                                             std::chrono::steady_clock::now());
        {
          std::lock_guard<std::mutex> lock(joint_state_mutex);
          latest_joint_state = std::move(evidence);
        }
        joint_state_condition.notify_all();
      });
  }

  moveit::planning_interface::MoveGroupInterface & moveGroup()
  {
    if (!move_group) {
      move_group = std::make_unique<moveit::planning_interface::MoveGroupInterface>(
        node, profile.planning_group);
      move_group->setEndEffectorLink(profile.tcp_link);
      move_group->setPoseReferenceFrame(profile.world_frame);
      move_group->setPlannerId(planner_id);
      move_group->setMaxVelocityScalingFactor(velocity_scaling);
      move_group->setMaxAccelerationScalingFactor(acceleration_scaling);
    }
    return *move_group;
  }

  rclcpp_action::Client<moveit_msgs::action::MoveGroup>::SharedPtr moveGroupAction()
  {
    if (!move_group_action) {
      move_group_action =
        rclcpp_action::create_client<moveit_msgs::action::MoveGroup>(node, "move_action");
    }
    return move_group_action;
  }

  moveit::planning_interface::PlanningSceneInterface & planningSceneInterface()
  {
    if (!planning_scene_interface) {
      planning_scene_interface =
        std::make_unique<moveit::planning_interface::PlanningSceneInterface>();
    }
    return *planning_scene_interface;
  }

  bool refreshScene()
  {
    auto & group = moveGroup();
    if (!group.startStateMonitor(state_timeout_seconds))
      return false;
    auto current = group.getCurrentState(state_timeout_seconds);
    if (!current)
      return false;
    auto next = std::make_shared<planning_scene::PlanningScene>(current->getRobotModel());
    next->setCurrentState(*current);
    auto & scene_interface = planningSceneInterface();
    const auto objects = scene_interface.getObjects();
    for (const auto & [id, object] : objects) {
      static_cast<void>(id);
      if (!next->processCollisionObjectMsg(object))
        return false;
    }
    const auto attached = scene_interface.getAttachedObjects();
    for (const auto & [id, object] : attached) {
      static_cast<void>(id);
      if (!next->processAttachedCollisionObjectMsg(object))
        return false;
    }
    std::lock_guard<std::mutex> lock(scene_mutex);
    scene = std::move(next);
    return true;
  }

  std::shared_ptr<rclcpp::Node> node;
  SO101Profile profile;
  std::string planner_id;
  double velocity_scaling;
  double acceleration_scaling;
  double state_timeout_seconds;
  std::unique_ptr<moveit::planning_interface::MoveGroupInterface> move_group;
  rclcpp_action::Client<moveit_msgs::action::MoveGroup>::SharedPtr move_group_action;
  std::unique_ptr<moveit::planning_interface::PlanningSceneInterface> planning_scene_interface;
  mutable std::mutex scene_mutex;
  std::shared_ptr<planning_scene::PlanningScene> scene;
  rclcpp::Subscription<sensor_msgs::msg::JointState>::SharedPtr joint_state_subscription;
  mutable std::mutex joint_state_mutex;
  std::condition_variable joint_state_condition;
  std::optional<CurrentJointStateEvidence> latest_joint_state;
  std::optional<MoveItJointPlanningDiagnostics> diagnostics;
  std::atomic<std::uint64_t> diagnostic_sequence{1};
};

namespace
{

MoveItJointPlanningBoundaryOptions legacyBoundaryOptions(std::string planner_id,
                                                         double velocity_scaling,
                                                         double acceleration_scaling,
                                                         double state_timeout_seconds)
{
  MoveItJointPlanningBoundaryOptions options;
  options.planner_id = std::move(planner_id);
  options.velocity_scaling = velocity_scaling;
  options.acceleration_scaling = acceleration_scaling;
  options.state_timeout_seconds = state_timeout_seconds;
  return options;
}

}  // namespace

MoveItJointPlanningBoundary::MoveItJointPlanningBoundary(
  std::shared_ptr<rclcpp::Node> node, SO101Profile profile, std::string planner_id,
  double velocity_scaling, double acceleration_scaling, double state_timeout_seconds) :
    MoveItJointPlanningBoundary(std::move(node), std::move(profile),
                                legacyBoundaryOptions(std::move(planner_id), velocity_scaling,
                                                      acceleration_scaling, state_timeout_seconds))
{
}

MoveItJointPlanningBoundary::MoveItJointPlanningBoundary(
  std::shared_ptr<rclcpp::Node> node, SO101Profile profile,
  MoveItJointPlanningBoundaryOptions options) :
    impl_(std::make_unique<Impl>(std::move(node), std::move(profile), std::move(options)))
{
}

MoveItJointPlanningBoundary::~MoveItJointPlanningBoundary() = default;

std::optional<CurrentJointStateEvidence> MoveItJointPlanningBoundary::currentState()
{
  std::unique_lock<std::mutex> lock(impl_->joint_state_mutex);
  if (!impl_->joint_state_condition.wait_for(
        lock, std::chrono::duration<double>(impl_->state_timeout_seconds),
        [this] { return impl_->latest_joint_state.has_value(); })) {
    return std::nullopt;
  }
  return impl_->latest_joint_state;
}

std::optional<MotionPlanningSceneFacts> MoveItJointPlanningBoundary::sceneFacts()
{
  if (!impl_->refreshScene())
    return std::nullopt;
  MotionPlanningSceneFacts facts;
  auto & scene_interface = impl_->planningSceneInterface();
  const auto objects = scene_interface.getObjects(
    {impl_->profile.table_object, impl_->profile.pedestal_object, impl_->profile.task_object_id});
  facts.table_in_world = objects.count(impl_->profile.table_object) == 1;
  facts.pedestal_in_world = objects.count(impl_->profile.pedestal_object) == 1;
  facts.task_object_in_world = objects.count(impl_->profile.task_object_id) == 1;
  if (facts.table_in_world) {
    facts.table_world_pose = poseFrom(objects.at(impl_->profile.table_object).pose);
  }
  if (facts.pedestal_in_world) {
    facts.pedestal_world_pose = poseFrom(objects.at(impl_->profile.pedestal_object).pose);
  }
  if (facts.task_object_in_world) {
    facts.task_object_world_pose = poseFrom(objects.at(impl_->profile.task_object_id).pose);
  }
  const auto attached = scene_interface.getAttachedObjects({impl_->profile.task_object_id});
  const auto found = attached.find(impl_->profile.task_object_id);
  facts.task_object_attached = found != attached.end();
  if (found != attached.end()) {
    facts.attached_link = found->second.link_name;
    facts.touch_links.insert(found->second.touch_links.begin(), found->second.touch_links.end());
    facts.attached_relative_pose = poseFrom(found->second.object.pose);
  }
  {
    std::lock_guard<std::mutex> lock(impl_->scene_mutex);
    if (impl_->scene && impl_->scene->knowsFrameTransform(impl_->profile.moveit_attach_link)) {
      facts.current_gripper_pose_world =
        updatedLinkPose(impl_->scene->getCurrentState(), impl_->profile.moveit_attach_link);
    }
    if (impl_->scene && impl_->scene->knowsFrameTransform(impl_->profile.tcp_link)) {
      facts.current_tcp_pose_world =
        updatedLinkPose(impl_->scene->getCurrentState(), impl_->profile.tcp_link);
    }
  }
  return facts;
}

ActionResult MoveItJointPlanningBoundary::execute(const MotionPlanArtifact & artifact)
{
  const auto trajectory =
    executableTrajectoryFromValidatedArtifact(artifact, impl_->profile.arm_joints);
  if (!trajectory) {
    return {ActionStatus::FAILED,
            Failure{FailureCategory::EXECUTION,
                    "MOTION_ARTIFACT_INVALID",
                    "MoveIt execution requires a complete validated SO-101 artifact",
                    {}}};
  }
  const auto result = impl_->moveGroup().execute(*trajectory);
  if (!static_cast<bool>(result)) {
    return {ActionStatus::FAILED, Failure{FailureCategory::EXECUTION,
                                          "MOVEIT_EXECUTION_FAILED",
                                          "MoveIt failed to execute the exact validated artifact",
                                          {}}};
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ActionResult MoveItJointPlanningBoundary::cancel()
{
  impl_->moveGroup().stop();
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

std::variant<MicroLiftPlanningCapture, ActionResult>
MoveItJointPlanningBoundary::captureWorldZMicroLiftPlanningRequest(const Pose3d & current_tcp_world,
                                                                   double world_z_delta_m)
{
  if (!std::isfinite(current_tcp_world.x) || !std::isfinite(current_tcp_world.y) ||
      !std::isfinite(current_tcp_world.z) || !std::isfinite(current_tcp_world.qx) ||
      !std::isfinite(current_tcp_world.qy) || !std::isfinite(current_tcp_world.qz) ||
      !std::isfinite(current_tcp_world.qw) || !std::isfinite(world_z_delta_m) ||
      world_z_delta_m <= 0.0 || world_z_delta_m > 0.002) {
    return ActionResult{
      ActionStatus::FAILED,
      Failure{FailureCategory::CONFIGURATION,
              "MICRO_LIFT_REQUEST_INVALID",
              "World-Z physical-grasp probe must be a finite positive lift no larger than 2 mm",
              {}}};
  }
  return captureWorldZPlanningRequest(current_tcp_world, current_tcp_world.z + world_z_delta_m);
}

std::variant<MicroLiftPlanningCapture, ActionResult>
MoveItJointPlanningBoundary::captureWorldZMicroDescendPlanningRequest(
  const Pose3d & current_tcp_world, double target_world_z_m)
{
  const auto displacement = current_tcp_world.z - target_world_z_m;
  if (!std::isfinite(current_tcp_world.x) || !std::isfinite(current_tcp_world.y) ||
      !std::isfinite(current_tcp_world.z) || !std::isfinite(current_tcp_world.qx) ||
      !std::isfinite(current_tcp_world.qy) || !std::isfinite(current_tcp_world.qz) ||
      !std::isfinite(current_tcp_world.qw) || !std::isfinite(target_world_z_m) ||
      target_world_z_m >= current_tcp_world.z ||
      displacement > 0.002 + kMicroLiftPositionToleranceM) {
    return ActionResult{
      ActionStatus::FAILED,
      Failure{FailureCategory::CONFIGURATION,
              "MICRO_DESCEND_TARGET_INVALID",
              "World-Z micro-descend target must be finite, lower, and no more than 2 mm away",
              {}}};
  }
  return captureWorldZPlanningRequest(current_tcp_world, target_world_z_m);
}

std::variant<MicroLiftPlanningCapture, ActionResult>
MoveItJointPlanningBoundary::captureWorldZPlanningRequest(const Pose3d & current_tcp_world,
                                                          double target_world_z_m)
{
  geometry_msgs::msg::PoseStamped target;
  target.header.frame_id = impl_->profile.world_frame;
  target.header.stamp = impl_->node->now();
  target.pose.position.x = current_tcp_world.x;
  target.pose.position.y = current_tcp_world.y;
  target.pose.position.z = target_world_z_m;
  target.pose.orientation.x = current_tcp_world.qx;
  target.pose.orientation.y = current_tcp_world.qy;
  target.pose.orientation.z = current_tcp_world.qz;
  target.pose.orientation.w = current_tcp_world.qw;
  auto & group = impl_->moveGroup();
  const auto current = group.getCurrentState(impl_->state_timeout_seconds);
  if (!current) {
    return ActionResult{ActionStatus::FAILED,
                        Failure{FailureCategory::OBSERVATION,
                                "MICRO_LIFT_CURRENT_STATE_TIMEOUT",
                                "MoveIt current state was unavailable before world-Z micro lift",
                                {}}};
  }
  if (!impl_->refreshScene()) {
    return ActionResult{
      ActionStatus::FAILED,
      Failure{FailureCategory::MOVEIT_SCENE,
              "MICRO_LIFT_SCENE_UNAVAILABLE",
              "Planning Scene was unavailable for request-scoped micro-lift planning",
              {}}};
  }
  MicroLiftPlanningCapture capture;
  capture.request.request.group_name = impl_->profile.planning_group;
  capture.request.request.planner_id = impl_->planner_id;
  capture.request.request.num_planning_attempts = 1;
  capture.request.request.allowed_planning_time = 5.0;
  capture.request.request.max_velocity_scaling_factor = 0.03;
  capture.request.request.max_acceleration_scaling_factor = 0.03;
  moveit::core::robotStateToRobotStateMsg(*current, capture.request.request.start_state, true);
  capture.request.request.goal_constraints.push_back(
    kinematic_constraints::constructGoalConstraints(impl_->profile.tcp_link, target,
                                                    kMicroLiftPositionToleranceM,
                                                    kMicroLiftOrientationToleranceRad));
  capture.request.planning_options.plan_only = true;
  capture.request.planning_options.planning_scene_diff.is_diff = true;
  {
    std::lock_guard<std::mutex> lock(impl_->scene_mutex);
    impl_->scene->getPlanningSceneMsg(capture.observed_scene);
    collision_detection::CollisionRequest collision_request;
    collision_request.group_name = impl_->profile.planning_group;
    collision_request.contacts = true;
    collision_request.max_contacts = 256;
    collision_request.max_contacts_per_pair = 1;
    collision_detection::AllowedCollisionMatrix raw_acm(impl_->scene->getAllowedCollisionMatrix());
    collision_detection::CollisionResult raw_result;
    impl_->scene->checkCollision(collision_request, raw_result, impl_->scene->getCurrentState(),
                                 raw_acm);
    collision_detection::AllowedCollisionMatrix request_acm(raw_acm);
    for (const auto & link : impl_->profile.moveit_touch_links) {
      request_acm.setEntry(impl_->profile.task_object_id, link, true);
    }
    collision_detection::CollisionResult request_result;
    impl_->scene->checkCollision(collision_request, request_result, impl_->scene->getCurrentState(),
                                 request_acm);
    request_acm.getMessage(
      capture.request.planning_options.planning_scene_diff.allowed_collision_matrix);
    capture.contacts.raw_collision = raw_result.collision;
    capture.contacts.request_collision = request_result.collision;
    for (const auto & [pair, contacts] : raw_result.contacts)
      capture.contacts.raw_contacts[pair.first + "|" + pair.second] = contacts.size();
    for (const auto & [pair, contacts] : request_result.contacts)
      capture.contacts.request_contacts[pair.first + "|" + pair.second] = contacts.size();
  }
  return capture;
}

ActionResult MoveItJointPlanningBoundary::executeWorldZMicroLift(const Pose3d & current_tcp_world,
                                                                 double world_z_delta_m)
{
  return executeWorldZPlanningRequest(current_tcp_world, world_z_delta_m, false);
}

ActionResult
MoveItJointPlanningBoundary::executeWorldZMicroDescend(const Pose3d & current_tcp_world,
                                                       double target_world_z_m)
{
  return executeWorldZPlanningRequest(current_tcp_world, target_world_z_m - current_tcp_world.z,
                                      true);
}

ActionResult MoveItJointPlanningBoundary::executeWorldZPlanningRequest(
  const Pose3d & current_tcp_world, double world_z_displacement_m, bool descend)
{
  auto captured =
    descend ? captureWorldZMicroDescendPlanningRequest(current_tcp_world,
                                                       current_tcp_world.z + world_z_displacement_m)
            : captureWorldZMicroLiftPlanningRequest(current_tcp_world, world_z_displacement_m);
  if (std::holds_alternative<ActionResult>(captured)) {
    auto failure = std::get<ActionResult>(std::move(captured));
    if (!descend || (failure.failure && failure.failure->code == "MICRO_DESCEND_TARGET_INVALID"))
      return failure;
    return {
      failure.status,
      Failure{failure.failure ? failure.failure->category : FailureCategory::PLANNING,
              "MICRO_DESCEND_PLANNING_FAILED",
              failure.failure ? failure.failure->message : "World-Z micro-descend planning failed",
              {}}};
  }
  const auto capture = std::get<MicroLiftPlanningCapture>(std::move(captured));
  auto client = impl_->moveGroupAction();
  if (!client->wait_for_action_server(
        std::chrono::duration<double>(impl_->state_timeout_seconds))) {
    return {ActionStatus::FAILED,
            Failure{FailureCategory::OBSERVATION,
                    descend ? "MICRO_DESCEND_PLANNING_FAILED" : "MICRO_LIFT_MOVE_GROUP_UNAVAILABLE",
                    descend
                      ? "MoveGroup action is unavailable for request-scoped micro-descend planning"
                      : "MoveGroup action is unavailable for request-scoped micro-lift planning",
                    {}}};
  }
  const auto record_failure = [&](const MicroLiftPlanningOutcome & outcome,
                                  const ActionResult & original) {
    if (!impl_->diagnostics || !impl_->diagnostics->sink || !outcome.failure_stage)
      return;
    PlanningFailureResultEvidence result{*outcome.failure_stage, original};
    result.transport_result_code = outcome.transport_result_code;
    result.cancel_acknowledged = outcome.cancel_acknowledged;
    result.cancel_terminal = outcome.terminal;
    if (outcome.result) {
      result.moveit_error_code = outcome.result->error_code.val;
      result.planning_time = outcome.result->planning_time;
      result.trajectory_joint_names =
        outcome.result->planned_trajectory.joint_trajectory.joint_names;
      const auto & points = outcome.result->planned_trajectory.joint_trajectory.points;
      result.trajectory_points = points.size();
      if (!points.empty())
        result.trajectory_duration_seconds = durationSeconds(points.back().time_from_start);
    }
    const auto captured_at = std::chrono::duration_cast<std::chrono::nanoseconds>(
                               std::chrono::system_clock::now().time_since_epoch())
                               .count();
    PlanningFailureArtifact artifact{
      captured_at,
      impl_->diagnostic_sequence.fetch_add(1, std::memory_order_relaxed),
      impl_->diagnostics->simulation_session_id,
      impl_->diagnostics->configuration_fingerprint,
      current_tcp_world,
      world_z_displacement_m,
      capture.request,
      capture.observed_scene,
      capture.contacts,
      impl_->profile,
      std::move(result)};
    std::optional<Failure> diagnostic_failure;
    try {
      diagnostic_failure = impl_->diagnostics->sink->record(artifact);
    } catch (const std::exception & error) {
      diagnostic_failure =
        Failure{FailureCategory::INTERNAL, "PLANNING_DIAGNOSTIC_WRITE_FAILED", error.what(), {}};
    } catch (...) {
      diagnostic_failure = Failure{FailureCategory::INTERNAL,
                                   "PLANNING_DIAGNOSTIC_WRITE_FAILED",
                                   "planning diagnostic sink threw an unknown exception",
                                   {}};
    }
    if (diagnostic_failure) {
      RCLCPP_WARN_THROTTLE(impl_->node->get_logger(), *impl_->node->get_clock(), 5000,
                           "PLANNING_DIAGNOSTIC_WRITE_FAILED: %s",
                           diagnostic_failure->message.c_str());
    }
  };
  const auto finish_failure = [&](const MicroLiftPlanningOutcome & outcome) {
    auto original = classifyMicroLiftPlanningOutcome(outcome);
    record_failure(outcome, original);
    if (!descend || original.status == ActionStatus::SUCCEEDED)
      return original;
    return ActionResult{original.status, Failure{original.failure->category,
                                                 "MICRO_DESCEND_PLANNING_FAILED",
                                                 original.failure->message,
                                                 {}}};
  };
  const auto goal_future = client->async_send_goal(capture.request);
  if (goal_future.wait_for(std::chrono::seconds(3)) != std::future_status::ready) {
    MicroLiftPlanningOutcome outcome;
    outcome.action = {ActionStatus::SUCCEEDED, std::nullopt};
    outcome.failure_stage = PlanningFailureStage::GOAL_ACCEPT_TIMEOUT;
    return finish_failure(outcome);
  }
  const auto & goal_handle = goal_future.get();
  if (!goal_handle) {
    MicroLiftPlanningOutcome outcome;
    outcome.action = {ActionStatus::SUCCEEDED, std::nullopt};
    outcome.failure_stage = PlanningFailureStage::GOAL_REJECTED;
    return finish_failure(outcome);
  }
  const auto result_future = client->async_get_result(goal_handle);
  if (result_future.wait_for(std::chrono::seconds(15)) != std::future_status::ready) {
    RosMoveGroupGoalCancellation cancellation(client, goal_handle, result_future);
    auto cleanup = cancelRequestScopedGoalAndWait(cancellation, impl_->state_timeout_seconds,
                                                  impl_->state_timeout_seconds);
    MicroLiftPlanningOutcome outcome;
    outcome.action = cleanup;
    outcome.failure_stage = PlanningFailureStage::RESULT_TIMEOUT;
    outcome.cancel_acknowledged = cancellation.cancelAcknowledged();
    outcome.terminal = cancellation.terminal();
    return finish_failure(outcome);
  }
  const auto & wrapped = result_future.get();
  MicroLiftPlanningOutcome outcome;
  outcome.action = {ActionStatus::SUCCEEDED, std::nullopt};
  outcome.transport_result_code = static_cast<std::int8_t>(wrapped.code);
  outcome.result = wrapped.result;
  if (wrapped.code != rclcpp_action::ResultCode::SUCCEEDED) {
    outcome.failure_stage = PlanningFailureStage::TRANSPORT_FAILURE;
  } else if (!wrapped.result) {
    outcome.failure_stage = PlanningFailureStage::MISSING_RESULT;
  } else if (wrapped.result->error_code.val != moveit_msgs::msg::MoveItErrorCodes::SUCCESS) {
    outcome.failure_stage = PlanningFailureStage::MOVEIT_ERROR;
  } else if (wrapped.result->planned_trajectory.joint_trajectory.points.empty()) {
    outcome.failure_stage = PlanningFailureStage::EMPTY_TRAJECTORY;
  }
  auto classified = classifyMicroLiftPlanningOutcome(outcome);
  if (classified.status != ActionStatus::SUCCEEDED) {
    record_failure(outcome, classified);
    return classified;
  }
  const auto executed = impl_->moveGroup().execute(wrapped.result->planned_trajectory);
  if (!static_cast<bool>(executed)) {
    return {
      ActionStatus::FAILED,
      Failure{FailureCategory::EXECUTION,
              descend ? "MICRO_DESCEND_EXECUTION_FAILED" : "MICRO_LIFT_MOVEIT_EXECUTION_FAILED",
              descend ? "MoveIt failed to execute the validated world-Z micro-descend plan"
                      : "MoveIt failed to execute the validated world-Z micro-lift plan",
              {}}};
  }
  if (descend) {
    const auto reached = poseFrom(impl_->moveGroup().getCurrentPose(impl_->profile.tcp_link).pose);
    const Vec3 expected_position{current_tcp_world.x, current_tcp_world.y,
                                 current_tcp_world.z + world_z_displacement_m};
    const Eigen::Quaterniond expected_orientation(current_tcp_world.qw, current_tcp_world.qx,
                                                  current_tcp_world.qy, current_tcp_world.qz);
    const Eigen::Quaterniond reached_orientation(reached.qw, reached.qx, reached.qy, reached.qz);
    const auto orientation_error =
      2.0 * std::acos(std::clamp(
              std::abs(expected_orientation.normalized().dot(reached_orientation.normalized())),
              0.0, 1.0));
    if (distance(reached, expected_position) > kMicroLiftPositionToleranceM ||
        orientation_error > kMicroLiftOrientationToleranceRad) {
      return {ActionStatus::FAILED,
              Failure{FailureCategory::POSTCONDITION,
                      "MICRO_DESCEND_ENDPOINT_OUTSIDE_TOLERANCE",
                      "World-Z micro-descend endpoint is outside position or orientation tolerance",
                      {}}};
    }
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ActionResult MoveItJointPlanningBoundary::cancelWorldZMicroLift()
{
  return cancel();
}

ActionResult MoveItJointPlanningBoundary::cancelWorldZMicroDescend()
{
  auto result = cancel();
  if (result.status != ActionStatus::SUCCEEDED) {
    return {result.status, Failure{FailureCategory::EXECUTION,
                                   "MICRO_DESCEND_CANCEL_FAILED",
                                   result.failure ? result.failure->message
                                                  : "World-Z micro-descend cancellation failed",
                                   {}}};
  }
  return result;
}

JointSegmentPlanResult MoveItJointPlanningBoundary::planSegment(
  const std::vector<std::string> & joint_names, const std::vector<double> & start,
  const std::vector<double> & goal, const std::set<std::string> & allowed_touch_pairs,
  const std::optional<TemporalContactPolicy> & temporal_contact_policy, double gripper_position,
  double velocity_scaling, double acceleration_scaling)
{
  if (joint_names != impl_->profile.arm_joints || start.size() != joint_names.size() ||
      goal.size() != joint_names.size() || !std::isfinite(gripper_position) ||
      !std::isfinite(velocity_scaling) || velocity_scaling <= 0.0 || velocity_scaling > 1.0 ||
      !std::isfinite(acceleration_scaling) || acceleration_scaling <= 0.0 ||
      acceleration_scaling > 1.0) {
    return planFail(FailureCategory::CONFIGURATION, "JOINT_SEGMENT_REQUEST_INVALID",
                    "MoveIt segment must contain the profile arm joint order");
  }
  if (!validTouchWhitelist(allowed_touch_pairs, impl_->profile)) {
    return planFail(
      FailureCategory::CONFIGURATION, "TOUCH_WHITELIST_POLICY_VIOLATION",
      "World touch whitelist must be empty or the exact SO-101 TaskObject touch policy");
  }
  if (!validTemporalContact(temporal_contact_policy, impl_->profile)) {
    return planFail(FailureCategory::CONFIGURATION, "TEMPORAL_CONTACT_POLICY_VIOLATION",
                    "Temporal contact pair and boundary location violate SO-101 policy");
  }
  auto & group = impl_->moveGroup();
  group.setMaxVelocityScalingFactor(velocity_scaling);
  group.setMaxAccelerationScalingFactor(acceleration_scaling);
  const auto current = group.getCurrentState(impl_->state_timeout_seconds);
  if (!current) {
    return planFail(FailureCategory::OBSERVATION, "CURRENT_STATE_TIMEOUT",
                    "MoveIt current state was unavailable before segment planning");
  }
  moveit::core::RobotState start_state(*current);
  start_state.setVariablePositions(joint_names, start);
  start_state.setVariablePosition(impl_->profile.gripper_joint, gripper_position);
  start_state.update();
  group.setStartState(start_state);
  group.clearPoseTargets();
  std::map<std::string, double> target;
  for (std::size_t i = 0; i < joint_names.size(); ++i)
    target.emplace(joint_names[i], goal[i]);
  if (!group.setJointValueTarget(target)) {
    return planFail(FailureCategory::PRECONDITION, "JOINT_TARGET_REJECTED",
                    "MoveIt rejected an out-of-bounds or invalid SO-101 joint target");
  }
  moveit_msgs::msg::RobotTrajectory planned_trajectory;
  int moveit_error_code = moveit_msgs::msg::MoveItErrorCodes::FAILURE;
  if (allowed_touch_pairs.empty() && !temporal_contact_policy) {
    moveit::planning_interface::MoveGroupInterface::Plan planned;
    const auto code = group.plan(planned);
    if (!static_cast<bool>(code)) {
      return planFail(FailureCategory::PLANNING, "MOVEIT_JOINT_PLAN_FAILED",
                      "MoveIt failed collision-aware joint-space planning");
    }
    planned_trajectory = std::move(planned.trajectory);
    moveit_error_code = code.val;
  } else {
    auto client = impl_->moveGroupAction();
    if (!client->wait_for_action_server(
          std::chrono::duration<double>(impl_->state_timeout_seconds))) {
      return planFail(FailureCategory::OBSERVATION, "MOVE_GROUP_ACTION_UNAVAILABLE",
                      "MoveGroup action is unavailable for request-scoped touch planning");
    }
    moveit_msgs::action::MoveGroup::Goal request;
    request.request.group_name = impl_->profile.planning_group;
    request.request.planner_id = impl_->planner_id;
    request.request.num_planning_attempts = 1;
    request.request.allowed_planning_time = 5.0;
    request.request.max_velocity_scaling_factor = velocity_scaling;
    request.request.max_acceleration_scaling_factor = acceleration_scaling;
    moveit::core::robotStateToRobotStateMsg(start_state, request.request.start_state, true);
    moveit::core::RobotState goal_state(start_state);
    goal_state.setVariablePositions(joint_names, goal);
    goal_state.update();
    const auto * joint_model_group =
      goal_state.getRobotModel()->getJointModelGroup(impl_->profile.planning_group);
    if (!joint_model_group) {
      return planFail(FailureCategory::CONFIGURATION, "PLANNING_GROUP_UNAVAILABLE",
                      "SO-101 arm planning group is unavailable");
    }
    request.request.goal_constraints.push_back(
      kinematic_constraints::constructGoalConstraints(goal_state, joint_model_group, 1e-4));
    request.planning_options.plan_only = true;
    request.planning_options.planning_scene_diff.is_diff = true;
    {
      std::lock_guard<std::mutex> lock(impl_->scene_mutex);
      if (!impl_->scene) {
        return planFail(FailureCategory::MOVEIT_SCENE, "PLANNING_SCENE_OBSERVATION_UNAVAILABLE",
                        "Planning Scene is unavailable for request-scoped touch planning");
      }
      collision_detection::AllowedCollisionMatrix acm(impl_->scene->getAllowedCollisionMatrix());
      for (const auto & link : impl_->profile.moveit_touch_links) {
        if (!allowed_touch_pairs.empty()) {
          acm.setEntry(impl_->profile.task_object_id, link, true);
        }
      }
      if (temporal_contact_policy) {
        if (temporal_contact_policy->allowed_pairs.find(policyPair(
              impl_->profile, impl_->profile.task_object_id, impl_->profile.table_object)) !=
            temporal_contact_policy->allowed_pairs.end()) {
          acm.setEntry(impl_->profile.task_object_id, impl_->profile.table_object, true);
        }
        for (const auto & link : impl_->profile.moveit_touch_links) {
          if (temporal_contact_policy->allowed_pairs.find(
                policyPair(impl_->profile, impl_->profile.task_object_id, link)) !=
              temporal_contact_policy->allowed_pairs.end()) {
            acm.setEntry(impl_->profile.task_object_id, link, true);
          }
        }
      }
      acm.getMessage(request.planning_options.planning_scene_diff.allowed_collision_matrix);
    }
    const auto goal_future = client->async_send_goal(request);
    if (goal_future.wait_for(std::chrono::seconds(3)) != std::future_status::ready) {
      return planFail(FailureCategory::PLANNING, "MOVE_GROUP_GOAL_TIMEOUT",
                      "MoveGroup did not accept the request-scoped planning goal in time");
    }
    const auto & goal_handle = goal_future.get();
    if (!goal_handle) {
      return planFail(FailureCategory::PLANNING, "MOVE_GROUP_GOAL_REJECTED",
                      "MoveGroup rejected the request-scoped planning goal");
    }
    const auto result_future = client->async_get_result(goal_handle);
    if (result_future.wait_for(std::chrono::seconds(15)) != std::future_status::ready) {
      RosMoveGroupGoalCancellation cancellation(client, goal_handle, result_future);
      const auto cleanup = cancelRequestScopedGoalAndWait(
        cancellation, impl_->state_timeout_seconds, impl_->state_timeout_seconds);
      if (cleanup.status != ActionStatus::SUCCEEDED) {
        return {cleanup, std::nullopt};
      }
      return planFail(FailureCategory::PLANNING, "MOVE_GROUP_RESULT_TIMEOUT",
                      "MoveGroup request-scoped planning did not finish in time");
    }
    const auto & wrapped = result_future.get();
    if (wrapped.code != rclcpp_action::ResultCode::SUCCEEDED || !wrapped.result ||
        wrapped.result->error_code.val != moveit_msgs::msg::MoveItErrorCodes::SUCCESS) {
      return planFail(FailureCategory::PLANNING, "MOVEIT_JOINT_PLAN_FAILED",
                      "MoveIt failed request-scoped touch-aware joint planning");
    }
    planned_trajectory = wrapped.result->planned_trajectory;
    moveit_error_code = wrapped.result->error_code.val;
  }
  const auto & trajectory = planned_trajectory.joint_trajectory;
  if (trajectory.points.empty()) {
    return planFail(FailureCategory::PLANNING, "EMPTY_MOTION_TRAJECTORY",
                    "MoveIt returned a successful but empty joint trajectory");
  }
  std::vector<std::size_t> indices;
  for (const auto & required : joint_names) {
    const auto it =
      std::find(trajectory.joint_names.begin(), trajectory.joint_names.end(), required);
    if (it == trajectory.joint_names.end()) {
      return planFail(FailureCategory::PLAN_VALIDATION, "TRAJECTORY_JOINT_ORDER_INCOMPLETE",
                      "MoveIt trajectory omits a required SO-101 arm joint");
    }
    indices.push_back(static_cast<std::size_t>(std::distance(trajectory.joint_names.begin(), it)));
  }
  JointSegmentPlan segment;
  segment.joint_names = joint_names;
  segment.moveit_success = true;
  segment.moveit_error_code = moveit_error_code;
  segment.planner_id = impl_->planner_id;
  segment.collision_aware = true;
  for (const auto & point : trajectory.points) {
    std::vector<double> positions;
    for (auto index : indices) {
      if (index >= point.positions.size()) {
        return planFail(FailureCategory::PLAN_VALIDATION, "TRAJECTORY_POINT_SHAPE_MISMATCH",
                        "MoveIt trajectory point omits a required joint position");
      }
      positions.push_back(point.positions[index]);
    }
    segment.points.push_back({std::move(positions), durationSeconds(point.time_from_start)});
  }
  return {{ActionStatus::SUCCEEDED, std::nullopt}, std::move(segment)};
}

std::optional<RobotStateEvidence> MoveItJointPlanningBoundary::evaluate(
  const std::vector<std::string> & joint_names, const std::vector<double> & joint_positions,
  const std::set<std::string> & allowed_touch_pairs,
  const std::optional<TemporalContactPolicy> & temporal_contact_policy,
  double gripper_position) const
{
  if (joint_names != impl_->profile.arm_joints || joint_positions.size() != joint_names.size() ||
      !std::isfinite(gripper_position)) {
    return std::nullopt;
  }
  if (!validTouchWhitelist(allowed_touch_pairs, impl_->profile))
    return std::nullopt;
  if (!validTemporalContact(temporal_contact_policy, impl_->profile))
    return std::nullopt;
  std::lock_guard<std::mutex> lock(impl_->scene_mutex);
  if (!impl_->scene)
    return std::nullopt;
  moveit::core::RobotState state(impl_->scene->getCurrentState());
  state.setVariablePositions(joint_names, joint_positions);
  state.setVariablePosition(impl_->profile.gripper_joint, gripper_position);
  state.update();
  if (!state.satisfiesBounds())
    return std::nullopt;
  RobotStateEvidence evidence;
  evidence.tcp_pose = poseFrom(state.getGlobalLinkTransform(impl_->profile.tcp_link));
  evidence.attached_task_object_pose_world =
    updatedAttachedBodyPose(state, impl_->profile.task_object_id);
  collision_detection::CollisionRequest request;
  request.group_name = impl_->profile.planning_group;
  request.contacts = true;
  request.max_contacts = 256;
  request.max_contacts_per_pair = 1;
  collision_detection::AllowedCollisionMatrix raw_acm(impl_->scene->getAllowedCollisionMatrix());
  if (!allowed_touch_pairs.empty()) {
    for (const auto & link : impl_->profile.moveit_touch_links) {
      raw_acm.setEntry(impl_->profile.task_object_id, link, false);
    }
  }
  if (temporal_contact_policy) {
    raw_acm.setEntry(impl_->profile.task_object_id, impl_->profile.table_object, false);
    for (const auto & link : impl_->profile.moveit_touch_links) {
      raw_acm.setEntry(impl_->profile.task_object_id, link, false);
    }
  }
  collision_detection::CollisionResult raw_result;
  impl_->scene->checkCollision(request, raw_result, state, raw_acm);
  for (const auto & item : raw_result.contacts) {
    evidence.raw_contact_pairs.insert(
      policyPair(impl_->profile, item.first.first, item.first.second));
  }
  collision_detection::AllowedCollisionMatrix allowed_acm(raw_acm);
  for (const auto & link : impl_->profile.moveit_touch_links) {
    if (!allowed_touch_pairs.empty()) {
      allowed_acm.setEntry(impl_->profile.task_object_id, link, true);
    }
  }
  if (temporal_contact_policy) {
    if (temporal_contact_policy->allowed_pairs.find(
          policyPair(impl_->profile, impl_->profile.task_object_id, impl_->profile.table_object)) !=
        temporal_contact_policy->allowed_pairs.end()) {
      allowed_acm.setEntry(impl_->profile.task_object_id, impl_->profile.table_object, true);
    }
    for (const auto & link : impl_->profile.moveit_touch_links) {
      if (temporal_contact_policy->allowed_pairs.find(
            policyPair(impl_->profile, impl_->profile.task_object_id, link)) !=
          temporal_contact_policy->allowed_pairs.end()) {
        allowed_acm.setEntry(impl_->profile.task_object_id, link, true);
      }
    }
  }
  collision_detection::CollisionResult allowed_result;
  impl_->scene->checkCollision(request, allowed_result, state, allowed_acm);
  evidence.collision_free = !allowed_result.collision;
  return evidence;
}

std::vector<CalibrationCandidate>
MoveItJointPlanningBoundary::search(const Vec3 & target_position, const Vec3 & local_axis,
                                    const Vec3 & target_axis, std::size_t seed_count,
                                    std::size_t result_count, double gripper_q6)
{
  if (!impl_->refreshScene() || seed_count == 0 || result_count == 0)
    return {};
  std::shared_ptr<planning_scene::PlanningScene> scene;
  {
    std::lock_guard<std::mutex> lock(impl_->scene_mutex);
    scene = impl_->scene;
  }
  const auto model = scene->getRobotModel();
  std::vector<std::pair<double, double>> bounds;
  for (const auto & name : impl_->profile.arm_joints) {
    const auto & bound = model->getVariableBounds(name);
    bounds.emplace_back(bound.min_position_, bound.max_position_);
  }
  const std::array<unsigned, 5> primes{2, 3, 5, 7, 11};
  std::vector<CalibrationCandidate> seeds;
  seeds.reserve(std::min<std::size_t>(seed_count, 64));
  auto score = [](const CalibrationCandidate & c) {
    return c.position_error + 0.12 * c.axis_error;
  };
  auto evaluate_candidate = [&](const std::vector<double> & joints, bool collision) {
    CalibrationCandidate candidate;
    candidate.joints = joints;
    moveit::core::RobotState state(scene->getCurrentState());
    state.setVariablePositions(impl_->profile.arm_joints, joints);
    state.setVariablePosition(impl_->profile.gripper_joint, gripper_q6);
    state.update();
    candidate.tcp_pose = poseFrom(state.getGlobalLinkTransform(impl_->profile.tcp_link));
    candidate.position_error = distance(candidate.tcp_pose, target_position);
    candidate.axis_error = approachAxisError(candidate.tcp_pose, local_axis, target_axis);
    candidate.collision_free = true;
    if (collision) {
      collision_detection::CollisionRequest request;
      request.group_name = impl_->profile.planning_group;
      request.contacts = true;
      request.distance = true;
      request.max_contacts = 32;
      request.max_contacts_per_pair = 1;
      collision_detection::CollisionResult result;
      scene->checkCollision(request, result, state);
      candidate.collision_free = !result.collision;
      candidate.minimum_distance = result.distance;
      for (const auto & [pair, contacts] : result.contacts) {
        static_cast<void>(contacts);
        candidate.collision_pairs.push_back(pair.first + ":" + pair.second);
      }
    }
    return candidate;
  };
  for (std::size_t i = 1; i <= seed_count; ++i) {
    std::vector<double> joints;
    joints.reserve(bounds.size());
    for (std::size_t j = 0; j < bounds.size(); ++j) {
      joints.push_back(bounds[j].first +
                       halton(i, primes[j]) * (bounds[j].second - bounds[j].first));
    }
    auto candidate = evaluate_candidate(joints, false);
    seeds.push_back(std::move(candidate));
    std::sort(seeds.begin(), seeds.end(),
              [&](const auto & a, const auto & b) { return score(a) < score(b); });
    if (seeds.size() > 64)
      seeds.pop_back();
  }

  std::vector<CalibrationCandidate> results;
  const Eigen::Vector3d target_axis_vector(target_axis.x, target_axis.y, target_axis.z);
  const Eigen::Vector3d normalized_target_axis = target_axis_vector.normalized();
  auto residual = [&](const CalibrationCandidate & candidate) {
    Eigen::Matrix<double, 6, 1> value;
    value << candidate.tcp_pose.x - target_position.x, candidate.tcp_pose.y - target_position.y,
      candidate.tcp_pose.z - target_position.z,
      0.12 * (rotatedAxis(candidate.tcp_pose, local_axis).x() - normalized_target_axis.x()),
      0.12 * (rotatedAxis(candidate.tcp_pose, local_axis).y() - normalized_target_axis.y()),
      0.12 * (rotatedAxis(candidate.tcp_pose, local_axis).z() - normalized_target_axis.z());
    return value;
  };
  for (auto candidate : seeds) {
    double damping = 1e-4;
    for (int iteration = 0; iteration < 100; ++iteration) {
      const auto base_residual = residual(candidate);
      const double base_cost = base_residual.squaredNorm();
      Eigen::Matrix<double, 6, 5> jacobian;
      constexpr double epsilon = 1e-5;
      for (std::size_t joint = 0; joint < candidate.joints.size(); ++joint) {
        auto perturbed = candidate.joints;
        perturbed[joint] =
          std::clamp(perturbed[joint] + epsilon, bounds[joint].first, bounds[joint].second);
        const double actual_step = perturbed[joint] - candidate.joints[joint];
        if (std::abs(actual_step) <= 1e-12) {
          perturbed[joint] = std::clamp(candidate.joints[joint] - epsilon, bounds[joint].first,
                                        bounds[joint].second);
        }
        const double signed_step = perturbed[joint] - candidate.joints[joint];
        jacobian.col(static_cast<Eigen::Index>(joint)) =
          (residual(evaluate_candidate(perturbed, false)) - base_residual) / signed_step;
      }
      const Eigen::Matrix<double, 5, 5> normal =
        jacobian.transpose() * jacobian + damping * Eigen::Matrix<double, 5, 5>::Identity();
      Eigen::Matrix<double, 5, 1> delta =
        normal.ldlt().solve(-jacobian.transpose() * base_residual);
      if (!delta.allFinite())
        break;
      const double max_delta = delta.cwiseAbs().maxCoeff();
      if (max_delta > 0.25)
        delta *= 0.25 / max_delta;
      auto proposal = candidate.joints;
      for (std::size_t joint = 0; joint < proposal.size(); ++joint) {
        proposal[joint] = std::clamp(proposal[joint] + delta[static_cast<Eigen::Index>(joint)],
                                     bounds[joint].first, bounds[joint].second);
      }
      auto tested = evaluate_candidate(proposal, false);
      if (residual(tested).squaredNorm() < base_cost) {
        candidate = std::move(tested);
        damping = std::max(1e-9, damping * 0.3);
      } else {
        damping = std::min(1e6, damping * 10.0);
      }
      if (residual(candidate).norm() < 1e-7 || delta.norm() < 1e-8)
        break;
    }
    candidate = evaluate_candidate(candidate.joints, true);
    results.push_back(std::move(candidate));
  }
  std::sort(results.begin(), results.end(),
            [&](const auto & a, const auto & b) { return score(a) < score(b); });
  results.erase(std::unique(results.begin(), results.end(),
                            [](const auto & a, const auto & b) {
                              double max_delta = 0.0;
                              for (std::size_t i = 0; i < a.joints.size(); ++i) {
                                max_delta =
                                  std::max(max_delta, std::abs(a.joints[i] - b.joints[i]));
                              }
                              return max_delta < 1e-4;
                            }),
                results.end());
  std::vector<CalibrationCandidate> selected;
  for (const auto & result : results) {
    if (selected.size() == result_count)
      break;
    selected.push_back(result);
  }
  std::size_t collision_free_count = 0;
  for (const auto & result : results) {
    if (!result.collision_free)
      continue;
    selected.push_back(result);
    if (++collision_free_count == result_count)
      break;
  }
  return selected;
}

}  // namespace so101_gazebo_demo::pick_place
