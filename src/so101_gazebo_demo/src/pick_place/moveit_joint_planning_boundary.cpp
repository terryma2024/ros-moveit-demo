#include "so101_gazebo_demo/pick_place/moveit_joint_planning_boundary.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
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
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>

namespace so101_gazebo_demo::pick_place
{
namespace
{

Pose3d poseFrom(const Eigen::Isometry3d & transform)
{
  const Eigen::Quaterniond q(transform.rotation());
  const auto & p = transform.translation();
  return {p.x(), p.y(), p.z(), q.x(), q.y(), q.z(), q.w()};
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
  return {{ActionStatus::FAILED,
           Failure{category, std::move(code), std::move(message), {}}}, std::nullopt};
}

std::string canonicalPair(std::string first, std::string second)
{
  if (second < first) std::swap(first, second);
  return first + ":" + second;
}

std::set<std::string> exactWorldTouchWhitelist(const SO101Profile & profile)
{
  std::set<std::string> result;
  for (const auto & link : profile.moveit_touch_links) {
    result.insert(canonicalPair(profile.coke_model, link));
  }
  return result;
}

bool validTouchWhitelist(const std::set<std::string> & requested,
                         const SO101Profile & profile)
{
  return requested.empty() || requested == exactWorldTouchWhitelist(profile);
}

bool validTemporalContact(const std::optional<TemporalContactPolicy> & requested,
                          const SO101Profile & profile)
{
  if (!requested) return true;
  const auto support = std::set<std::string>{canonicalPair(profile.coke_model,
                                                            profile.table_object)};
  const auto gripper = exactWorldTouchWhitelist(profile);
  if (requested->location == TemporalContactLocation::FIRST_ONLY) {
    return requested->max_axial_clearance_m == 0.0 &&
           (requested->allowed_pairs == support || requested->allowed_pairs == gripper);
  }
  if (requested->location == TemporalContactLocation::LAST_ONLY) {
    return requested->max_axial_clearance_m == 0.0 &&
           requested->allowed_pairs == support;
  }
  return requested->location == TemporalContactLocation::PREFIX_UNTIL_AXIAL_CLEARANCE &&
         requested->allowed_pairs == gripper &&
         std::isfinite(requested->max_axial_clearance_m) &&
         requested->max_axial_clearance_m > 0.0;
}

}  // namespace

class MoveItJointPlanningBoundary::Impl
{
public:
  Impl(std::shared_ptr<rclcpp::Node> node, SO101Profile profile, std::string planner_id,
       double velocity_scaling, double acceleration_scaling, double state_timeout_seconds)
  : node(std::move(node)), profile(std::move(profile)), planner_id(std::move(planner_id)),
    velocity_scaling(velocity_scaling), acceleration_scaling(acceleration_scaling),
    state_timeout_seconds(state_timeout_seconds)
  {
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
      move_group_action = rclcpp_action::create_client<moveit_msgs::action::MoveGroup>(
        node, "move_action");
    }
    return move_group_action;
  }

  bool refreshScene()
  {
    auto & group = moveGroup();
    if (!group.startStateMonitor(state_timeout_seconds)) return false;
    auto current = group.getCurrentState(state_timeout_seconds);
    if (!current) return false;
    auto next = std::make_shared<planning_scene::PlanningScene>(current->getRobotModel());
    next->setCurrentState(*current);
    const auto objects = planning_scene_interface.getObjects();
    for (const auto & [id, object] : objects) {
      static_cast<void>(id);
      if (!next->processCollisionObjectMsg(object)) return false;
    }
    const auto attached = planning_scene_interface.getAttachedObjects();
    for (const auto & [id, object] : attached) {
      static_cast<void>(id);
      if (!next->processAttachedCollisionObjectMsg(object)) return false;
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
  moveit::planning_interface::PlanningSceneInterface planning_scene_interface;
  mutable std::mutex scene_mutex;
  std::shared_ptr<planning_scene::PlanningScene> scene;
};

MoveItJointPlanningBoundary::MoveItJointPlanningBoundary(
  std::shared_ptr<rclcpp::Node> node, SO101Profile profile, std::string planner_id,
  double velocity_scaling, double acceleration_scaling, double state_timeout_seconds)
: impl_(std::make_unique<Impl>(std::move(node), std::move(profile), std::move(planner_id),
                              velocity_scaling, acceleration_scaling, state_timeout_seconds))
{
}

MoveItJointPlanningBoundary::~MoveItJointPlanningBoundary() = default;

std::optional<CurrentJointStateEvidence> MoveItJointPlanningBoundary::currentState()
{
  auto & group = impl_->moveGroup();
  if (!group.startStateMonitor(impl_->state_timeout_seconds)) return std::nullopt;
  const auto state = group.getCurrentState(impl_->state_timeout_seconds);
  if (!state) return std::nullopt;
  CurrentJointStateEvidence result;
  result.joint_names = impl_->profile.arm_joints;
  for (const auto & name : result.joint_names) result.positions.push_back(state->getVariablePosition(name));
  result.observed_stamp_nanoseconds = static_cast<std::uint64_t>(impl_->node->now().nanoseconds());
  return result;
}

std::optional<MotionPlanningSceneFacts> MoveItJointPlanningBoundary::sceneFacts()
{
  if (!impl_->refreshScene()) return std::nullopt;
  MotionPlanningSceneFacts facts;
  const auto objects = impl_->planning_scene_interface.getObjects(
    {impl_->profile.table_object, impl_->profile.coke_model});
  facts.table_in_world = objects.count(impl_->profile.table_object) == 1;
  facts.coke_in_world = objects.count(impl_->profile.coke_model) == 1;
  const auto attached = impl_->planning_scene_interface.getAttachedObjects({impl_->profile.coke_model});
  const auto found = attached.find(impl_->profile.coke_model);
  facts.coke_attached = found != attached.end();
  if (found != attached.end()) {
    facts.attached_link = found->second.link_name;
    facts.touch_links.insert(found->second.touch_links.begin(), found->second.touch_links.end());
  }
  return facts;
}

JointSegmentPlanResult MoveItJointPlanningBoundary::planSegment(
  const std::vector<std::string> & joint_names, const std::vector<double> & start,
  const std::vector<double> & goal, const std::set<std::string> & allowed_touch_pairs,
  const std::optional<TemporalContactPolicy> & temporal_contact_policy,
  double gripper_position)
{
  if (joint_names != impl_->profile.arm_joints || start.size() != joint_names.size() ||
      goal.size() != joint_names.size() || !std::isfinite(gripper_position)) {
    return planFail(FailureCategory::CONFIGURATION, "JOINT_SEGMENT_REQUEST_INVALID",
                    "MoveIt segment must contain the profile arm joint order");
  }
  if (!validTouchWhitelist(allowed_touch_pairs, impl_->profile)) {
    return planFail(FailureCategory::CONFIGURATION, "TOUCH_WHITELIST_POLICY_VIOLATION",
                    "World touch whitelist must be empty or the exact SO-101 Coke touch policy");
  }
  if (!validTemporalContact(temporal_contact_policy, impl_->profile)) {
    return planFail(FailureCategory::CONFIGURATION, "TEMPORAL_CONTACT_POLICY_VIOLATION",
                    "Temporal contact pair and boundary location violate SO-101 policy");
  }
  auto & group = impl_->moveGroup();
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
  for (std::size_t i = 0; i < joint_names.size(); ++i) target.emplace(joint_names[i], goal[i]);
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
    request.request.max_velocity_scaling_factor = impl_->velocity_scaling;
    request.request.max_acceleration_scaling_factor = impl_->acceleration_scaling;
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
      collision_detection::AllowedCollisionMatrix acm(
        impl_->scene->getAllowedCollisionMatrix());
      for (const auto & link : impl_->profile.moveit_touch_links) {
        if (!allowed_touch_pairs.empty()) {
          acm.setEntry(impl_->profile.coke_model, link, true);
        }
      }
      if (temporal_contact_policy) {
        if (temporal_contact_policy->allowed_pairs.find(
              canonicalPair(impl_->profile.coke_model, impl_->profile.table_object)) !=
            temporal_contact_policy->allowed_pairs.end()) {
          acm.setEntry(impl_->profile.coke_model, impl_->profile.table_object, true);
        }
        for (const auto & link : impl_->profile.moveit_touch_links) {
          if (temporal_contact_policy->allowed_pairs.find(
                canonicalPair(impl_->profile.coke_model, link)) !=
              temporal_contact_policy->allowed_pairs.end()) {
            acm.setEntry(impl_->profile.coke_model, link, true);
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
    const auto goal_handle = goal_future.get();
    if (!goal_handle) {
      return planFail(FailureCategory::PLANNING, "MOVE_GROUP_GOAL_REJECTED",
                      "MoveGroup rejected the request-scoped planning goal");
    }
    const auto result_future = client->async_get_result(goal_handle);
    if (result_future.wait_for(std::chrono::seconds(15)) != std::future_status::ready) {
      client->async_cancel_goal(goal_handle);
      return planFail(FailureCategory::PLANNING, "MOVE_GROUP_RESULT_TIMEOUT",
                      "MoveGroup request-scoped planning did not finish in time");
    }
    const auto wrapped = result_future.get();
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
    const auto it = std::find(trajectory.joint_names.begin(), trajectory.joint_names.end(), required);
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
  const std::vector<std::string> & joint_names,
  const std::vector<double> & joint_positions,
  const std::set<std::string> & allowed_touch_pairs,
  const std::optional<TemporalContactPolicy> & temporal_contact_policy,
  double gripper_position) const
{
  if (joint_names != impl_->profile.arm_joints || joint_positions.size() != joint_names.size() ||
      !std::isfinite(gripper_position)) {
    return std::nullopt;
  }
  if (!validTouchWhitelist(allowed_touch_pairs, impl_->profile)) return std::nullopt;
  if (!validTemporalContact(temporal_contact_policy, impl_->profile)) return std::nullopt;
  std::lock_guard<std::mutex> lock(impl_->scene_mutex);
  if (!impl_->scene) return std::nullopt;
  moveit::core::RobotState state(impl_->scene->getCurrentState());
  state.setVariablePositions(joint_names, joint_positions);
  state.setVariablePosition(impl_->profile.gripper_joint, gripper_position);
  state.update();
  if (!state.satisfiesBounds()) return std::nullopt;
  RobotStateEvidence evidence;
  evidence.tcp_pose = poseFrom(state.getGlobalLinkTransform(impl_->profile.tcp_link));
  collision_detection::CollisionRequest request;
  request.group_name = impl_->profile.planning_group;
  request.contacts = true;
  request.max_contacts = 256;
  request.max_contacts_per_pair = 1;
  collision_detection::AllowedCollisionMatrix raw_acm(
    impl_->scene->getAllowedCollisionMatrix());
  if (!allowed_touch_pairs.empty()) {
    for (const auto & link : impl_->profile.moveit_touch_links) {
      raw_acm.setEntry(impl_->profile.coke_model, link, false);
    }
  }
  if (temporal_contact_policy) {
    raw_acm.setEntry(impl_->profile.coke_model, impl_->profile.table_object, false);
    for (const auto & link : impl_->profile.moveit_touch_links) {
      raw_acm.setEntry(impl_->profile.coke_model, link, false);
    }
  }
  collision_detection::CollisionResult raw_result;
  impl_->scene->checkCollision(request, raw_result, state, raw_acm);
  for (const auto & item : raw_result.contacts) {
    evidence.raw_contact_pairs.insert(canonicalPair(item.first.first, item.first.second));
  }
  collision_detection::AllowedCollisionMatrix allowed_acm(raw_acm);
  for (const auto & link : impl_->profile.moveit_touch_links) {
    if (!allowed_touch_pairs.empty()) {
      allowed_acm.setEntry(impl_->profile.coke_model, link, true);
    }
  }
  if (temporal_contact_policy) {
    if (temporal_contact_policy->allowed_pairs.find(
          canonicalPair(impl_->profile.coke_model, impl_->profile.table_object)) !=
        temporal_contact_policy->allowed_pairs.end()) {
      allowed_acm.setEntry(impl_->profile.coke_model, impl_->profile.table_object, true);
    }
    for (const auto & link : impl_->profile.moveit_touch_links) {
      if (temporal_contact_policy->allowed_pairs.find(
            canonicalPair(impl_->profile.coke_model, link)) !=
          temporal_contact_policy->allowed_pairs.end()) {
        allowed_acm.setEntry(impl_->profile.coke_model, link, true);
      }
    }
  }
  collision_detection::CollisionResult allowed_result;
  impl_->scene->checkCollision(request, allowed_result, state, allowed_acm);
  evidence.collision_free = !allowed_result.collision;
  return evidence;
}

std::vector<CalibrationCandidate> MoveItJointPlanningBoundary::search(
  const Vec3 & target_position, const Vec3 & local_axis, const Vec3 & target_axis,
  std::size_t seed_count, std::size_t result_count, double gripper_q6)
{
  if (!impl_->refreshScene() || seed_count == 0 || result_count == 0) return {};
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
    for (std::size_t j = 0; j < bounds.size(); ++j) {
      joints.push_back(bounds[j].first + halton(i, primes[j]) *
                        (bounds[j].second - bounds[j].first));
    }
    auto candidate = evaluate_candidate(joints, false);
    seeds.push_back(std::move(candidate));
    std::sort(seeds.begin(), seeds.end(), [&](const auto & a, const auto & b) {
      return score(a) < score(b);
    });
    if (seeds.size() > 64) seeds.pop_back();
  }

  std::vector<CalibrationCandidate> results;
  const Eigen::Vector3d target_axis_vector(target_axis.x, target_axis.y, target_axis.z);
  const Eigen::Vector3d normalized_target_axis = target_axis_vector.normalized();
  auto residual = [&](const CalibrationCandidate & candidate) {
    Eigen::Matrix<double, 6, 1> value;
    value << candidate.tcp_pose.x - target_position.x,
      candidate.tcp_pose.y - target_position.y,
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
        perturbed[joint] = std::clamp(perturbed[joint] + epsilon,
                                      bounds[joint].first, bounds[joint].second);
        const double actual_step = perturbed[joint] - candidate.joints[joint];
        if (std::abs(actual_step) <= 1e-12) {
          perturbed[joint] = std::clamp(candidate.joints[joint] - epsilon,
                                        bounds[joint].first, bounds[joint].second);
        }
        const double signed_step = perturbed[joint] - candidate.joints[joint];
        jacobian.col(static_cast<Eigen::Index>(joint)) =
          (residual(evaluate_candidate(perturbed, false)) - base_residual) / signed_step;
      }
      const Eigen::Matrix<double, 5, 5> normal =
        jacobian.transpose() * jacobian + damping * Eigen::Matrix<double, 5, 5>::Identity();
      Eigen::Matrix<double, 5, 1> delta = normal.ldlt().solve(-jacobian.transpose() * base_residual);
      if (!delta.allFinite()) break;
      const double max_delta = delta.cwiseAbs().maxCoeff();
      if (max_delta > 0.25) delta *= 0.25 / max_delta;
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
      if (residual(candidate).norm() < 1e-7 || delta.norm() < 1e-8) break;
    }
    candidate = evaluate_candidate(candidate.joints, true);
    results.push_back(std::move(candidate));
  }
  std::sort(results.begin(), results.end(), [&](const auto & a, const auto & b) {
    return score(a) < score(b);
  });
  results.erase(std::unique(results.begin(), results.end(), [](const auto & a, const auto & b) {
    double max_delta = 0.0;
    for (std::size_t i = 0; i < a.joints.size(); ++i) {
      max_delta = std::max(max_delta, std::abs(a.joints[i] - b.joints[i]));
    }
    return max_delta < 1e-4;
  }), results.end());
  std::vector<CalibrationCandidate> selected;
  for (const auto & result : results) {
    if (selected.size() == result_count) break;
    selected.push_back(result);
  }
  std::size_t collision_free_count = 0;
  for (const auto & result : results) {
    if (!result.collision_free) continue;
    selected.push_back(result);
    if (++collision_free_count == result_count) break;
  }
  return selected;
}

}  // namespace so101_gazebo_demo::pick_place
