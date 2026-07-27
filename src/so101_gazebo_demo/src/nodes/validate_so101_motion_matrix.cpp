#include <cstdlib>
#include <algorithm>
#include <cmath>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <memory>
#include <limits>
#include <optional>
#include <set>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include <Eigen/Geometry>
#include <moveit/planning_scene_interface/planning_scene_interface.hpp>
#include <moveit/robot_model_loader/robot_model_loader.hpp>
#include <moveit/robot_state/robot_state.hpp>
#include <moveit_msgs/msg/attached_collision_object.hpp>
#include <moveit_msgs/msg/planning_scene.hpp>
#include <rclcpp/rclcpp.hpp>

#include "so101_gazebo_demo/pick_place/moveit_joint_planning_boundary.hpp"
#include "so101_gazebo_demo/pick_place/moveit_scene_adapter.hpp"
#include "so101_gazebo_demo/pick_place/node_spinner.hpp"
#include "so101_gazebo_demo/pick_place/follow_joint_trajectory_gripper_adapter.hpp"
#include "so101_gazebo_demo/pick_place/gazebo_attachment_executor.hpp"
#include "so101_gazebo_demo/pick_place/gazebo_reset_adapter.hpp"
#include "so101_gazebo_demo/pick_place/gazebo_world_observer.hpp"
#include "so101_gazebo_demo/pick_place/so101_fixed_motion_targets.hpp"

namespace spp = so101_gazebo_demo::pick_place;

namespace
{

geometry_msgs::msg::Pose poseMessage(const Eigen::Isometry3d & transform)
{
  geometry_msgs::msg::Pose result;
  const Eigen::Quaterniond q(transform.rotation());
  result.position.x = transform.translation().x();
  result.position.y = transform.translation().y();
  result.position.z = transform.translation().z();
  result.orientation.x = q.x();
  result.orientation.y = q.y();
  result.orientation.z = q.z();
  result.orientation.w = q.w();
  return result;
}

Eigen::Isometry3d transform(const spp::Pose3d & pose)
{
  Eigen::Isometry3d result = Eigen::Isometry3d::Identity();
  result.translation() = Eigen::Vector3d(pose.x, pose.y, pose.z);
  result.linear() = Eigen::Quaterniond(pose.qw, pose.qx, pose.qy, pose.qz).normalized().toRotationMatrix();
  return result;
}

spp::Pose3d pose(const Eigen::Isometry3d & transform)
{
  const Eigen::Quaterniond q(transform.rotation());
  return {transform.translation().x(), transform.translation().y(),
          transform.translation().z(), q.x(), q.y(), q.z(), q.w()};
}

spp::Pose3d pose(const geometry_msgs::msg::Pose & value)
{
  return {value.position.x, value.position.y, value.position.z,
          value.orientation.x, value.orientation.y, value.orientation.z,
          value.orientation.w};
}

double positionError(const spp::Pose3d & first, const spp::Pose3d & second)
{
  return std::hypot(std::hypot(first.x - second.x, first.y - second.y),
                    first.z - second.z);
}

double orientationError(const spp::Pose3d & first, const spp::Pose3d & second)
{
  const double first_norm = std::sqrt(first.qx * first.qx + first.qy * first.qy +
                                      first.qz * first.qz + first.qw * first.qw);
  const double second_norm = std::sqrt(second.qx * second.qx + second.qy * second.qy +
                                       second.qz * second.qz + second.qw * second.qw);
  if (!std::isfinite(first_norm) || !std::isfinite(second_norm) ||
      first_norm <= 1e-12 || second_norm <= 1e-12) {
    return std::numeric_limits<double>::infinity();
  }
  const double dot = std::abs((first.qx * second.qx + first.qy * second.qy +
                               first.qz * second.qz + first.qw * second.qw) /
                              (first_norm * second_norm));
  return 2.0 * std::acos(std::clamp(dot, 0.0, 1.0));
}

bool poseMatches(const spp::Pose3d & first, const spp::Pose3d & second,
                 const spp::SO101Profile & profile)
{
  return positionError(first, second) <= profile.coke_position_drift_tolerance &&
         orientationError(first, second) <= profile.coke_orientation_drift_tolerance_rad;
}

spp::Pose3d compose(const spp::Pose3d & parent, const spp::Pose3d & child)
{
  return pose(transform(parent) * transform(child));
}

class SceneSeeder
{
public:
  SceneSeeder(std::shared_ptr<rclcpp::Node> node, spp::SO101Profile profile)
  : profile_(std::move(profile)), loader_(node, "robot_description", false),
    gripper_coke_(transform(profile_.calibrated_grasp_relative_pose))
  {
    if (!loader_.getModel()) {
      throw std::runtime_error("robot model unavailable for matrix scene seed");
    }
  }

  bool seedCarrying()
  {
    if (!ensureTable() || !removeAttached()) return false;
    auto remove = worldCoke(profile_.coke_pose);
    remove.operation = moveit_msgs::msg::CollisionObject::REMOVE;
    if (!scene_.applyCollisionObject(remove)) return false;

    moveit_msgs::msg::PlanningScene diff;
    diff.is_diff = true;
    diff.robot_state.is_diff = true;
    moveit_msgs::msg::AttachedCollisionObject attached;
    attached.link_name = profile_.moveit_attach_link;
    attached.touch_links = profile_.moveit_touch_links;
    attached.object = worldCoke(profile_.coke_pose);
    attached.object.header.frame_id = profile_.moveit_attach_link;
    attached.object.pose = poseMessage(gripper_coke_);
    attached.object.operation = moveit_msgs::msg::CollisionObject::ADD;
    diff.robot_state.attached_collision_objects.push_back(attached);
    if (!scene_.applyPlanningScene(diff)) return false;
    const auto world = scene_.getObjects({profile_.coke_model});
    const auto attached_readback = scene_.getAttachedObjects({profile_.coke_model});
    const auto found = attached_readback.find(profile_.coke_model);
    if (!world.empty() || found == attached_readback.end() ||
        found->second.link_name != profile_.moveit_attach_link ||
        std::set<std::string>(found->second.touch_links.begin(), found->second.touch_links.end()) !=
          std::set<std::string>(profile_.moveit_touch_links.begin(), profile_.moveit_touch_links.end())) {
      return false;
    }
    const auto observed = pose(found->second.object.pose);
    relative_position_error_ =
      positionError(observed, profile_.calibrated_grasp_relative_pose);
    relative_orientation_error_ =
      orientationError(observed, profile_.calibrated_grasp_relative_pose);
    return relative_position_error_ <= 1e-9 && relative_orientation_error_ <= 1e-9;
  }

  bool seedDetached(const spp::Pose3d & coke_pose)
  {
    if (!ensureTable() || !removeAttached() ||
        !scene_.applyCollisionObject(worldCoke(coke_pose))) return false;
    const auto objects = scene_.getObjects({profile_.table_object, profile_.coke_model});
    const auto found = objects.find(profile_.coke_model);
    const auto table = objects.find(profile_.table_object);
    return scene_.getAttachedObjects({profile_.coke_model}).empty() &&
           found != objects.end() && table != objects.end() &&
           poseMatches(pose(found->second.pose), coke_pose, profile_) &&
           poseMatches(pose(table->second.pose), profile_.table_pose, profile_);
  }

  double relativePositionError() const noexcept { return relative_position_error_; }
  double relativeOrientationError() const noexcept { return relative_orientation_error_; }

private:
  bool ensureTable()
  {
    const spp::MoveItSceneGeometry geometry{
      profile_.world_frame, profile_.table_object, profile_.table_size,
      profile_.coke_model, profile_.coke_height, profile_.coke_radius};
    if (!scene_.applyCollisionObject(
          spp::makeTableCollisionObject(geometry, profile_.table_pose))) {
      return false;
    }
    const auto objects = scene_.getObjects({profile_.table_object});
    const auto found = objects.find(profile_.table_object);
    return found != objects.end() &&
           poseMatches(pose(found->second.pose), profile_.table_pose, profile_);
  }

  bool removeAttached()
  {
    moveit_msgs::msg::PlanningScene diff;
    diff.is_diff = true;
    diff.robot_state.is_diff = true;
    moveit_msgs::msg::AttachedCollisionObject remove;
    remove.link_name = profile_.moveit_attach_link;
    remove.object.id = profile_.coke_model;
    remove.object.operation = moveit_msgs::msg::CollisionObject::REMOVE;
    diff.robot_state.attached_collision_objects.push_back(remove);
    return scene_.applyPlanningScene(diff);
  }

  moveit_msgs::msg::CollisionObject worldCoke(const spp::Pose3d & pose) const
  {
    return spp::makeCokeCollisionObject(
      {profile_.world_frame, profile_.table_object, profile_.table_size,
       profile_.coke_model, profile_.coke_height, profile_.coke_radius}, pose);
  }

  spp::SO101Profile profile_;
  robot_model_loader::RobotModelLoader loader_;
  moveit::planning_interface::PlanningSceneInterface scene_;
  Eigen::Isometry3d gripper_coke_;
  double relative_position_error_{0.0};
  double relative_orientation_error_{0.0};
};

class MatrixBoundary final : public spp::IJointPlanningBoundary,
                             public spp::IRobotStateEvidenceProvider
{
public:
  explicit MatrixBoundary(std::shared_ptr<spp::MoveItJointPlanningBoundary> real)
  : real_(std::move(real)) {}

  std::optional<spp::CurrentJointStateEvidence> currentState() override
  {
    if (!current_) return std::nullopt;
    auto result = *current_;
    result.joint_names = {"1", "2", "3", "4", "5"};
    result.positions = logical_start_;
    result.velocities.assign(logical_start_.size(), 0.0);
    return result;
  }
  std::optional<spp::MotionPlanningSceneFacts> sceneFacts() override
  {
    return real_->sceneFacts();
  }
  spp::JointSegmentPlanResult planSegment(
    const std::vector<std::string> & names, const std::vector<double> & start,
    const std::vector<double> & goal, const std::set<std::string> & allowed,
    const std::optional<spp::TemporalContactPolicy> & temporal,
    double gripper_position) override
  {
    return real_->planSegment(names, start, goal, allowed, temporal, gripper_position);
  }
  std::optional<spp::RobotStateEvidence> evaluate(
    const std::vector<std::string> & names, const std::vector<double> & positions,
    const std::set<std::string> & allowed,
    const std::optional<spp::TemporalContactPolicy> & temporal,
    double gripper_position) const override
  {
    return real_->evaluate(names, positions, allowed, temporal, gripper_position);
  }
  void setLogicalStart(std::vector<double> start, spp::CurrentJointStateEvidence current)
  {
    logical_start_ = std::move(start);
    current_ = std::move(current);
  }

private:
  std::shared_ptr<spp::MoveItJointPlanningBoundary> real_;
  std::vector<double> logical_start_;
  std::optional<spp::CurrentJointStateEvidence> current_;
};

class MatrixMoveItObserver final : public spp::IWorldObserver
{
public:
  MatrixMoveItObserver(std::shared_ptr<spp::MoveItJointPlanningBoundary> boundary,
                       spp::SO101Profile profile)
  : boundary_(std::move(boundary)), profile_(std::move(profile)) {}

  spp::ObservationResult observe() override
  {
    const auto current = boundary_->currentState();
    const auto scene = boundary_->sceneFacts();
    if (!current || !scene || !current->gripper_position || !current->gripper_velocity) {
      return {std::nullopt,
              spp::Failure{spp::FailureCategory::OBSERVATION,
                           "MATRIX_MOVEIT_OBSERVATION_UNAVAILABLE",
                           "Matrix could not independently read current joints and Planning Scene",
                           {}}};
    }
    spp::WorldSnapshot snapshot;
    snapshot.fresh = true;
    snapshot.arm_stationary = current->velocities.size() == profile_.arm_joints.size();
    for (const double velocity : current->velocities) {
      snapshot.arm_stationary = snapshot.arm_stationary && std::isfinite(velocity) &&
                                std::abs(velocity) <= profile_.q6_velocity_tolerance;
    }
    snapshot.joint_positions[profile_.gripper_joint] = *current->gripper_position;
    snapshot.joint_velocities[profile_.gripper_joint] = *current->gripper_velocity;
    if (scene->table_world_pose) {
      snapshot.moveit_world_object_poses[profile_.table_object] = *scene->table_world_pose;
    }
    if (scene->coke_world_pose) {
      snapshot.moveit_world_object_poses[profile_.coke_model] = *scene->coke_world_pose;
    }
    snapshot.moveit_coke_attached = scene->coke_attached;
    snapshot.moveit_coke_attached_link = scene->attached_link;
    snapshot.moveit_coke_touch_links = scene->touch_links;
    return {snapshot, std::nullopt};
  }

private:
  std::shared_ptr<spp::MoveItJointPlanningBoundary> boundary_;
  spp::SO101Profile profile_;
};

std::optional<spp::CurrentJointStateEvidence> waitForQ6(
  const std::shared_ptr<spp::MoveItJointPlanningBoundary> & boundary,
  double expected, const spp::SO101Profile & profile)
{
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(10);
  while (std::chrono::steady_clock::now() < deadline) {
    auto current = boundary->currentState();
    if (current && current->gripper_position && current->gripper_velocity &&
        std::isfinite(*current->gripper_position) &&
        std::isfinite(*current->gripper_velocity) &&
        std::abs(*current->gripper_position - expected) <= profile.q6_tolerance &&
        std::abs(*current->gripper_velocity) <= profile.q6_velocity_tolerance) {
      return current;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
  }
  return std::nullopt;
}

bool waitForGazebo(const std::shared_ptr<spp::GazeboResetAdapter> & adapter,
                   bool attached, const spp::Pose3d & expected,
                   const spp::SO101Profile & profile)
{
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
  while (std::chrono::steady_clock::now() < deadline) {
    const auto observed = adapter->observe();
    if (observed && observed->coke_attached == attached &&
        poseMatches(observed->coke_world_pose, expected, profile)) {
      return true;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
  }
  return false;
}

bool commandAttachment(spp::GazeboAttachmentExecutor & executor, spp::State state)
{
  spp::ExecutionContext context;
  context.state = state;
  context.next_state = spp::State::ERROR;
  return executor.execute(context).status == spp::ActionStatus::SUCCEEDED;
}

bool setupDetachedGazebo(const std::shared_ptr<spp::GazeboResetAdapter> & adapter,
                         spp::GazeboAttachmentExecutor & detach,
                         const spp::Pose3d & expected,
                         const spp::SO101Profile & profile)
{
  const auto before = adapter->observe();
  if (!before || (before->coke_attached &&
                  !commandAttachment(detach, spp::State::DETACH_GAZEBO)) ||
      adapter->setCokeWorldPose(expected).status != spp::ActionStatus::SUCCEEDED) {
    return false;
  }
  return waitForGazebo(adapter, false, expected, profile);
}

bool setupCarryingGazebo(const std::shared_ptr<spp::GazeboResetAdapter> & adapter,
                         spp::GazeboAttachmentExecutor & detach,
                         spp::GazeboAttachmentExecutor & attach,
                         const spp::Pose3d & expected,
                         const spp::SO101Profile & profile)
{
  if (!setupDetachedGazebo(adapter, detach, expected, profile) ||
      !commandAttachment(attach, spp::State::ATTACH_GAZEBO)) {
    return false;
  }
  return waitForGazebo(adapter, true, expected, profile);
}

std::string joins(const std::vector<double> & values)
{
  std::ostringstream out;
  out << std::setprecision(9);
  for (std::size_t i = 0; i < values.size(); ++i) {
    if (i) out << ',';
    out << values[i];
  }
  return out.str();
}

std::string pairs(const std::set<std::string> & values)
{
  if (values.empty()) return "-";
  std::ostringstream out;
  for (const auto & value : values) out << value << ',';
  return out.str();
}

std::string temporal(const std::optional<spp::TemporalContactPolicy> & policy)
{
  if (!policy) return "-";
  std::string location;
  switch (policy->location) {
    case spp::TemporalContactLocation::FIRST_ONLY: location = "FIRST_ONLY"; break;
    case spp::TemporalContactLocation::LAST_ONLY: location = "LAST_ONLY"; break;
    case spp::TemporalContactLocation::PREFIX_UNTIL_AXIAL_CLEARANCE:
      location = "PREFIX_UNTIL_AXIAL_CLEARANCE";
      break;
  }
  std::ostringstream out;
  out << location << ':' << pairs(policy->allowed_pairs);
  if (policy->location == spp::TemporalContactLocation::PREFIX_UNTIL_AXIAL_CLEARANCE) {
    out << "max_axial=" << policy->max_axial_clearance_m;
  }
  return out.str();
}

std::string rawSampleDetails(const spp::MotionPlanArtifact & artifact,
                             const spp::Vec3 & path_direction)
{
  std::ostringstream out;
  bool first = true;
  const auto & origin = artifact.samples.front().tcp_pose;
  const double direction_norm = std::sqrt(path_direction.x * path_direction.x +
                                           path_direction.y * path_direction.y +
                                           path_direction.z * path_direction.z);
  const double ux = path_direction.x / direction_norm;
  const double uy = path_direction.y / direction_norm;
  const double uz = path_direction.z / direction_norm;
  for (std::size_t i = 0; i < artifact.samples.size(); ++i) {
    if (artifact.samples[i].raw_contact_pairs.empty()) continue;
    const auto & pose = artifact.samples[i].tcp_pose;
    const double dx = pose.x - origin.x;
    const double dy = pose.y - origin.y;
    const double dz = pose.z - origin.z;
    const double axial = dx * ux + dy * uy + dz * uz;
    const double lateral = std::sqrt(
      (dx - axial * ux) * (dx - axial * ux) +
      (dy - axial * uy) * (dy - axial * uy) +
      (dz - axial * uz) * (dz - axial * uz));
    if (!first) out << ';';
    out << i << ":axial=" << std::setprecision(9) << axial
        << ":lateral=" << lateral
        << ":pairs=" << pairs(artifact.samples[i].raw_contact_pairs);
    first = false;
  }
  return first ? "-" : out.str();
}

}  // namespace

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::NodeOptions options;
  options.automatically_declare_parameters_from_overrides(true);
  options.parameter_overrides({rclcpp::Parameter("use_sim_time", true)});
  auto node = std::make_shared<rclcpp::Node>("validate_so101_motion_matrix", options);
  auto spinner = std::make_unique<spp::NodeSpinner>(node);
  const auto profile = spp::SO101Profile::canonical();
  spp::SO101FixedMotionTargetPolicy policy(profile);
  SceneSeeder seeder(node, profile);
  auto real = std::make_shared<spp::MoveItJointPlanningBoundary>(node, profile);
  auto boundary = std::make_shared<MatrixBoundary>(real);
  auto adapter = std::make_shared<spp::ProfiledJointMotionAdapter>(boundary, boundary, profile);
  auto policy_ptr = std::make_shared<spp::SO101FixedMotionTargetPolicy>(profile);
  spp::SO101MotionPlanner planner(policy_ptr, adapter, profile);
  auto trajectory_client =
    std::make_shared<spp::RosTrajectoryActionClient>(node, profile.gripper_action);
  spp::FollowJointTrajectoryGripperAdapter gripper(trajectory_client, 1.0, 8.0);
  auto gazebo_reset = std::make_shared<spp::GazeboResetAdapter>(
    profile.gazebo_world, profile.coke_model, profile.detach_topic,
    profile.attachment_state_topic, 2.0, 3000);
  spp::GazeboAttachmentExecutor gazebo_attach(
    spp::State::ATTACH_GAZEBO, true, profile.attach_topic, profile.detach_topic,
    profile.attachment_event_topic, 3.0, 0.05, false);
  spp::GazeboAttachmentExecutor gazebo_detach(
    spp::State::DETACH_GAZEBO, false, profile.attach_topic, profile.detach_topic,
    profile.attachment_event_topic, 3.0, 0.05, false);
  MatrixMoveItObserver moveit_observer(real, profile);
  spp::GazeboWorldObserver observer(
    moveit_observer, profile.gazebo_world, profile.coke_model,
    profile.attachment_state_topic, "task4-live-matrix", 2.0, 3, 0.02,
    profile.coke_position_drift_tolerance,
    profile.coke_orientation_drift_tolerance_rad, false);
  const std::vector<spp::State> states{
    spp::State::MOVE_ABOVE_OBJECT, spp::State::DESCEND, spp::State::LIFT,
    spp::State::MOVE_ABOVE_PLACE, spp::State::DESCEND_TO_PLACE, spp::State::RETREAT,
    spp::State::RECOVER_LIFT_TO_SAFE_HEIGHT, spp::State::RECOVER_MOVE_ABOVE_PICK,
    spp::State::RECOVER_DESCEND_TO_PICK, spp::State::RECOVER_RETREAT};
  int failures = 0;
  for (const auto state : states) {
    const auto spec = policy.spec(state);
    const bool carrying = spp::isCarryingMotionState(state);
    if (!spec || gripper.command(spec ? spec->expected_gripper_q6 : 0.0).status !=
                   spp::ActionStatus::SUCCEEDED) {
      std::cout << "MATRIX state=" << spp::toString(state)
                << " status=FAIL setup=gripper_command\n";
      ++failures;
      continue;
    }
    const auto current = waitForQ6(real, spec->expected_gripper_q6, profile);
    const auto physical_scene = real->sceneFacts();
    const bool current_gripper_pose_valid =
      physical_scene && physical_scene->current_gripper_pose_world &&
      poseMatches(*physical_scene->current_gripper_pose_world,
                  *physical_scene->current_gripper_pose_world, profile);
    const auto detached_pose = state == spp::State::RETREAT ?
      profile.place_coke_pose : profile.coke_pose;
    const auto carrying_pose = physical_scene && physical_scene->current_gripper_pose_world ?
      std::optional<spp::Pose3d>{compose(*physical_scene->current_gripper_pose_world,
                                        profile.calibrated_grasp_relative_pose)} :
      std::nullopt;
    const bool gazebo_setup = carrying ?
      (carrying_pose && setupCarryingGazebo(gazebo_reset, gazebo_detach, gazebo_attach,
                                            *carrying_pose, profile)) :
      setupDetachedGazebo(gazebo_reset, gazebo_detach, detached_pose, profile);
    const bool moveit_setup = carrying ? seeder.seedCarrying() : seeder.seedDetached(detached_pose);
    if (!current || !current_gripper_pose_valid || !gazebo_setup || !moveit_setup) {
      std::cout << "MATRIX state=" << spp::toString(state)
                << " status=FAIL setup=current_q6_gripper_pose_gazebo_moveit"
                << " current=" << static_cast<bool>(current)
                << " gripper_pose=" << current_gripper_pose_valid
                << " gazebo=" << gazebo_setup << " moveit=" << moveit_setup << '\n';
      ++failures;
      continue;
    }
    const auto observation = observer.observe();
    if (!observation.snapshot) {
      std::cout << "MATRIX state=" << spp::toString(state)
                << " status=FAIL observation="
                << (observation.failure ? observation.failure->code : "UNKNOWN") << '\n';
      ++failures;
      continue;
    }
    boundary->setLogicalStart(spec->logical_start, *current);
    const auto planned = planner.plan(state, spp::State::ERROR, observation);
    const auto artifact = std::dynamic_pointer_cast<const spp::MotionPlanArtifact>(planned.artifact);
    spp::ValidationResult validated;
    if (artifact) {
      validated = spec->target.ladder ? spp::validateWaypointLadder(*artifact, spec->validation)
                                      : spp::validateJointGoalPlan(*artifact, spec->validation);
    }
    const bool attached_samples_complete = artifact &&
      (!carrying || std::all_of(artifact->samples.begin(), artifact->samples.end(),
        [](const auto & sample) { return sample.attached_coke_pose_world.has_value(); }));
    const bool pass = artifact && validated.ok && attached_samples_complete;
    if (!pass) ++failures;
    const auto start_evidence = real->evaluate(profile.arm_joints, spec->logical_start,
                                               spec->validation.allowed_touch_pairs,
                                               spec->validation.temporal_contact_policy,
                                               spec->expected_gripper_q6);
    std::cout << "MATRIX state=" << spp::toString(state)
              << " status=" << (pass ? "PASS" : "FAIL")
              << " scene=" << (carrying ? "attached" : "world")
              << " q6_observed=" << std::setprecision(9)
              << observation.snapshot->joint_positions.at(profile.gripper_joint)
              << " q6_velocity_observed="
              << observation.snapshot->joint_velocities.at(profile.gripper_joint)
              << " gazebo_attached=" << *observation.snapshot->gazebo_coke_attached
              << " touch=" << pairs(spec->validation.allowed_touch_pairs)
              << " temporal=" << temporal(spec->validation.temporal_contact_policy)
              << " start=" << joins(spec->logical_start)
              << " goal=" << joins(spec->target.joint_waypoints.back());
    if (carrying) {
      std::cout << " attached_relative_position_error=" << seeder.relativePositionError()
                << " attached_relative_orientation_error="
                << seeder.relativeOrientationError();
    }
    if (artifact) {
      std::cout << " points=" << artifact->trajectory_points
                << " attached_pose_samples="
                << std::count_if(artifact->samples.begin(), artifact->samples.end(),
                  [](const auto & sample) { return sample.attached_coke_pose_world.has_value(); })
                << " raw=" << pairs(artifact->raw_contact_pairs)
                << " raw_samples=" << rawSampleDetails(*artifact,
                                                        spec->validation.path_direction);
    }
    if (!pass) {
      const auto failure = planned.action.failure ? planned.action.failure :
        (!validated.failures.empty() ? std::optional<spp::Failure>{validated.failures.front()}
                                     : std::nullopt);
      std::cout << " code=" << (failure ? failure->code : "UNKNOWN");
      if (start_evidence) std::cout << " start_raw=" << pairs(start_evidence->raw_contact_pairs);
    }
    std::cout << '\n';
  }
  const bool final_reset =
    gripper.command(profile.q6_preopen).status == spp::ActionStatus::SUCCEEDED &&
    waitForQ6(real, profile.q6_preopen, profile).has_value() &&
    setupDetachedGazebo(gazebo_reset, gazebo_detach, profile.coke_pose, profile) &&
    seeder.seedDetached(profile.coke_pose);
  const auto final_observation = final_reset ? observer.observe() : spp::ObservationResult{};
  const bool final_readback = final_observation.snapshot &&
    final_observation.snapshot->gazebo_coke_attached &&
    !*final_observation.snapshot->gazebo_coke_attached &&
    final_observation.snapshot->gazebo_coke_pose_world &&
    poseMatches(*final_observation.snapshot->gazebo_coke_pose_world, profile.coke_pose, profile) &&
    final_observation.snapshot->moveit_world_object_poses.count(profile.coke_model) == 1 &&
    poseMatches(final_observation.snapshot->moveit_world_object_poses.at(profile.coke_model),
                profile.coke_pose, profile);
  std::cout << "MATRIX_FINAL_RESET status=" << (final_readback ? "PASS" : "FAIL") << '\n';
  if (!final_readback) ++failures;
  spinner.reset();
  rclcpp::shutdown();
  return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
