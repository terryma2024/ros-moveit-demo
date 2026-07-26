#include <cstdlib>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <memory>
#include <set>
#include <sstream>
#include <string>
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

class SceneSeeder
{
public:
  SceneSeeder(std::shared_ptr<rclcpp::Node> node, spp::SO101Profile profile,
              const std::vector<double> & pick_joints)
  : profile_(std::move(profile)), loader_(node, "robot_description", false)
  {
    const auto model = loader_.getModel();
    if (!model) throw std::runtime_error("robot model unavailable for matrix scene seed");
    moveit::core::RobotState state(model);
    state.setToDefaultValues();
    state.setVariablePositions(profile_.arm_joints, pick_joints);
    state.setVariablePosition(profile_.gripper_joint, profile_.q6_contact);
    state.update();
    const auto world_gripper = state.getGlobalLinkTransform(profile_.moveit_attach_link);
    gripper_coke_ = world_gripper.inverse() * transform(profile_.coke_pose);
  }

  bool seedCarrying()
  {
    if (!removeAttached()) return false;
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
    const auto & observed = found->second.object.pose;
    const auto expected = poseMessage(gripper_coke_);
    relative_pose_error_ = std::hypot(std::hypot(observed.position.x - expected.position.x,
                                                 observed.position.y - expected.position.y),
                                      observed.position.z - expected.position.z);
    return relative_pose_error_ <= 1e-9;
  }

  bool seedDetached(const spp::Pose3d & coke_pose)
  {
    if (!removeAttached() || !scene_.applyCollisionObject(worldCoke(coke_pose))) return false;
    return scene_.getAttachedObjects({profile_.coke_model}).empty() &&
           scene_.getObjects({profile_.coke_model}).size() == 1;
  }

  double relativePoseError() const noexcept { return relative_pose_error_; }

private:
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
  double relative_pose_error_{0.0};
};

class MatrixBoundary final : public spp::IJointPlanningBoundary,
                             public spp::IRobotStateEvidenceProvider
{
public:
  explicit MatrixBoundary(std::shared_ptr<spp::MoveItJointPlanningBoundary> real)
  : real_(std::move(real)) {}

  std::optional<spp::CurrentJointStateEvidence> currentState() override
  {
    return spp::CurrentJointStateEvidence{{"1", "2", "3", "4", "5"}, logical_start_, 1};
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
  void setLogicalStart(std::vector<double> start) { logical_start_ = std::move(start); }

private:
  std::shared_ptr<spp::MoveItJointPlanningBoundary> real_;
  std::vector<double> logical_start_;
};

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
  const auto pick_spec = policy.spec(spp::State::DESCEND);
  if (!pick_spec) return EXIT_FAILURE;
  SceneSeeder seeder(node, profile, pick_spec->target.joint_waypoints.back());
  auto real = std::make_shared<spp::MoveItJointPlanningBoundary>(node, profile);
  auto boundary = std::make_shared<MatrixBoundary>(real);
  auto adapter = std::make_shared<spp::ProfiledJointMotionAdapter>(boundary, boundary, profile);
  auto policy_ptr = std::make_shared<spp::SO101FixedMotionTargetPolicy>(profile);
  spp::SO101MotionPlanner planner(policy_ptr, adapter, profile);
  spp::WorldSnapshot snapshot;
  snapshot.fresh = true;
  snapshot.arm_stationary = true;
  const spp::ObservationResult observation{snapshot, std::nullopt};
  const std::vector<spp::State> states{
    spp::State::MOVE_ABOVE_OBJECT, spp::State::DESCEND, spp::State::LIFT,
    spp::State::MOVE_ABOVE_PLACE, spp::State::DESCEND_TO_PLACE, spp::State::RETREAT,
    spp::State::RECOVER_LIFT_TO_SAFE_HEIGHT, spp::State::RECOVER_MOVE_ABOVE_PICK,
    spp::State::RECOVER_DESCEND_TO_PICK, spp::State::RECOVER_RETREAT};
  int failures = 0;
  for (const auto state : states) {
    const auto spec = policy.spec(state);
    const bool carrying = spp::isCarryingMotionState(state);
    spp::Pose3d detached_pose = profile.coke_pose;
    if (state == spp::State::RETREAT) {
      detached_pose.x = -0.08;
      detached_pose.y = -0.25;
    }
    if (!spec || !(carrying ? seeder.seedCarrying() : seeder.seedDetached(detached_pose))) {
      std::cout << "MATRIX state=" << spp::toString(state) << " status=FAIL scene_seed=0\n";
      ++failures;
      continue;
    }
    boundary->setLogicalStart(spec->logical_start);
    const auto planned = planner.plan(state, spp::State::ERROR, observation);
    const auto artifact = std::dynamic_pointer_cast<const spp::MotionPlanArtifact>(planned.artifact);
    spp::ValidationResult validated;
    if (artifact) {
      validated = spec->target.ladder ? spp::validateWaypointLadder(*artifact, spec->validation)
                                      : spp::validateJointGoalPlan(*artifact, spec->validation);
    }
    const bool pass = artifact && validated.ok;
    if (!pass) ++failures;
    const auto start_evidence = real->evaluate(profile.arm_joints, spec->logical_start,
                                               spec->validation.allowed_touch_pairs,
                                               spec->validation.temporal_contact_policy,
                                               spec->expected_gripper_q6);
    std::cout << "MATRIX state=" << spp::toString(state)
              << " status=" << (pass ? "PASS" : "FAIL")
              << " scene=" << (carrying ? "attached" : "world")
              << " q6=" << std::setprecision(9) << spec->expected_gripper_q6
              << " touch=" << pairs(spec->validation.allowed_touch_pairs)
              << " temporal=" << temporal(spec->validation.temporal_contact_policy)
              << " start=" << joins(spec->logical_start)
              << " goal=" << joins(spec->target.joint_waypoints.back());
    if (carrying) std::cout << " attached_relative_position_error=" << seeder.relativePoseError();
    if (artifact) {
      std::cout << " points=" << artifact->trajectory_points
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
  if (!seeder.seedDetached(profile.coke_pose)) ++failures;
  spinner.reset();
  rclcpp::shutdown();
  return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
