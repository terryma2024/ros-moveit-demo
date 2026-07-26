#include "so101_gazebo_demo/pick_place/moveit_joint_planning_boundary.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <map>
#include <mutex>
#include <utility>

#include <Eigen/Geometry>
#include <moveit/move_group_interface/move_group_interface.hpp>
#include <moveit/planning_scene/planning_scene.hpp>
#include <moveit/planning_scene_interface/planning_scene_interface.hpp>
#include <moveit/robot_state/robot_state.hpp>
#include <rclcpp/rclcpp.hpp>

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
  const std::vector<double> & goal)
{
  if (joint_names != impl_->profile.arm_joints || start.size() != joint_names.size() ||
      goal.size() != joint_names.size()) {
    return planFail(FailureCategory::CONFIGURATION, "JOINT_SEGMENT_REQUEST_INVALID",
                    "MoveIt segment must contain the profile arm joint order");
  }
  auto & group = impl_->moveGroup();
  const auto current = group.getCurrentState(impl_->state_timeout_seconds);
  if (!current) {
    return planFail(FailureCategory::OBSERVATION, "CURRENT_STATE_TIMEOUT",
                    "MoveIt current state was unavailable before segment planning");
  }
  moveit::core::RobotState start_state(*current);
  start_state.setVariablePositions(joint_names, start);
  start_state.update();
  group.setStartState(start_state);
  group.clearPoseTargets();
  std::map<std::string, double> target;
  for (std::size_t i = 0; i < joint_names.size(); ++i) target.emplace(joint_names[i], goal[i]);
  if (!group.setJointValueTarget(target)) {
    return planFail(FailureCategory::PRECONDITION, "JOINT_TARGET_REJECTED",
                    "MoveIt rejected an out-of-bounds or invalid SO-101 joint target");
  }
  moveit::planning_interface::MoveGroupInterface::Plan planned;
  const auto code = group.plan(planned);
  if (!static_cast<bool>(code)) {
    return planFail(FailureCategory::PLANNING, "MOVEIT_JOINT_PLAN_FAILED",
                    "MoveIt failed collision-aware joint-space planning");
  }
  const auto & trajectory = planned.trajectory.joint_trajectory;
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
  segment.moveit_error_code = code.val;
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
  const std::vector<double> & joint_positions) const
{
  if (joint_names != impl_->profile.arm_joints || joint_positions.size() != joint_names.size()) {
    return std::nullopt;
  }
  std::lock_guard<std::mutex> lock(impl_->scene_mutex);
  if (!impl_->scene) return std::nullopt;
  moveit::core::RobotState state(impl_->scene->getCurrentState());
  state.setVariablePositions(joint_names, joint_positions);
  state.update();
  if (!state.satisfiesBounds()) return std::nullopt;
  RobotStateEvidence evidence;
  evidence.tcp_pose = poseFrom(state.getGlobalLinkTransform(impl_->profile.tcp_link));
  evidence.collision_free = !impl_->scene->isStateColliding(state, impl_->profile.planning_group, false);
  return evidence;
}

std::vector<CalibrationCandidate> MoveItJointPlanningBoundary::search(
  const Vec3 & target_position, const Vec3 & local_axis, const Vec3 & target_axis,
  std::size_t seed_count, std::size_t result_count)
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
    state.update();
    candidate.tcp_pose = poseFrom(state.getGlobalLinkTransform(impl_->profile.tcp_link));
    candidate.position_error = distance(candidate.tcp_pose, target_position);
    candidate.axis_error = approachAxisError(candidate.tcp_pose, local_axis, target_axis);
    candidate.collision_free = !collision ||
      !scene->isStateColliding(state, impl_->profile.planning_group, false);
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
  for (auto candidate : seeds) {
    std::vector<double> step;
    for (const auto & bound : bounds) step.push_back(0.12 * (bound.second - bound.first));
    for (int iteration = 0; iteration < 100; ++iteration) {
      bool improved = false;
      for (std::size_t joint = 0; joint < candidate.joints.size(); ++joint) {
        for (double sign : {-1.0, 1.0}) {
          auto proposal = candidate.joints;
          proposal[joint] = std::clamp(proposal[joint] + sign * step[joint],
                                       bounds[joint].first, bounds[joint].second);
          auto tested = evaluate_candidate(proposal, false);
          if (score(tested) + 1e-12 < score(candidate)) {
            candidate = std::move(tested);
            improved = true;
          }
        }
      }
      if (!improved) {
        for (auto & value : step) value *= 0.5;
      }
      if (*std::max_element(step.begin(), step.end()) < 1e-6) break;
    }
    candidate = evaluate_candidate(candidate.joints, true);
    if (candidate.collision_free) results.push_back(std::move(candidate));
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
  if (results.size() > result_count) results.resize(result_count);
  return results;
}

}  // namespace so101_gazebo_demo::pick_place
