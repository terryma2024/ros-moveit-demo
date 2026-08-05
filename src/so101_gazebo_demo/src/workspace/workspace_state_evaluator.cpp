#include "so101_gazebo_demo/workspace/workspace_state_evaluator.hpp"

#include <algorithm>
#include <cmath>
#include <set>
#include <stdexcept>

#include <Eigen/Geometry>
#include <moveit/collision_detection/collision_common.h>
#include <moveit/planning_scene/planning_scene.hpp>
#include <moveit/robot_model_loader/robot_model_loader.hpp>
#include <moveit/robot_state/robot_state.hpp>

#include "so101_gazebo_demo/pick_place/moveit_scene_adapter.hpp"

namespace so101_gazebo_demo::workspace
{
namespace
{
WorkspaceEvaluatorBuildResult failure(std::string code, std::string message)
{
  return {nullptr, WorkspaceFailure{std::move(code), std::move(message)}};
}

pick_place::Pose3d poseFromTransform(const Eigen::Isometry3d & transform)
{
  const auto & translation = transform.translation();
  Eigen::Quaterniond quaternion(transform.rotation());
  quaternion.normalize();
  if (!translation.allFinite() || !quaternion.coeffs().allFinite()) {
    throw std::runtime_error("TCP transform is not finite");
  }
  bool negate = quaternion.w() < 0.0;
  if (quaternion.w() == 0.0) {
    negate = quaternion.z() < 0.0 ||
             (quaternion.z() == 0.0 &&
              (quaternion.y() < 0.0 || (quaternion.y() == 0.0 && quaternion.x() < 0.0)));
  }
  if (negate)
    quaternion.coeffs() = -quaternion.coeffs();
  return {translation.x(), translation.y(), translation.z(), quaternion.x(),
          quaternion.y(),  quaternion.z(),  quaternion.w()};
}
}  // namespace

class WorkspaceStateEvaluator::Impl
{
public:
  Impl(moveit::core::RobotModelPtr model, pick_place::SO101Profile profile) :
      model_(std::move(model)), scene_(std::make_shared<planning_scene::PlanningScene>(model_)),
      state_(model_), profile_(std::move(profile))
  {
    const pick_place::MoveItSceneGeometry geometry{profile_.world_frame,
                                                   profile_.table_object,
                                                   profile_.table_size,
                                                   profile_.pedestal_object,
                                                   profile_.pedestal_size,
                                                   profile_.task_object_id,
                                                   profile_.task_object_height,
                                                   profile_.task_object_outer_radius,
                                                   profile_.task_object_wall_thickness,
                                                   profile_.task_object_bottom_thickness,
                                                   profile_.task_object_side_count};
    if (!scene_->processCollisionObjectMsg(
          pick_place::makeTableCollisionObject(geometry, profile_.table_pose))) {
      throw std::runtime_error("failed to insert canonical table");
    }
    if (!scene_->processCollisionObjectMsg(
          pick_place::makePedestalCollisionObject(geometry, profile_.pedestal_pose))) {
      throw std::runtime_error("failed to insert canonical pedestal");
    }
    state_.setToDefaultValues();
  }

  PoseSample evaluate(std::uint64_t sample_id, const GeneratedJointSample & generated)
  {
    for (std::size_t index = 0; index < profile_.arm_joints.size(); ++index) {
      state_.setVariablePosition(profile_.arm_joints[index], generated.arm_joints[index]);
    }
    state_.setVariablePosition(profile_.gripper_joint, profile_.q6_preopen);
    state_.update();
    PoseSample sample{};
    sample.sample_id = sample_id;
    sample.source = generated.source;
    sample.arm_joints = generated.arm_joints;
    sample.gripper_q6 = profile_.q6_preopen;
    sample.bounds_valid = state_.satisfiesBounds();
    sample.tcp_pose = poseFromTransform(state_.getGlobalLinkTransform(profile_.tcp_link));

    collision_detection::CollisionRequest self_request;
    collision_detection::CollisionResult self_result;
    scene_->checkSelfCollision(self_request, self_result, state_,
                               scene_->getAllowedCollisionMatrix());
    sample.self_collision = self_result.collision;

    collision_detection::CollisionRequest full_request;
    full_request.contacts = true;
    full_request.max_contacts = 256;
    full_request.max_contacts_per_pair = 1;
    collision_detection::CollisionResult full_result;
    scene_->checkCollision(full_request, full_result, state_, scene_->getAllowedCollisionMatrix());
    const std::set<std::string> scene_ids{profile_.table_object, profile_.pedestal_object};
    for (const auto & [names, contacts] : full_result.contacts) {
      static_cast<void>(contacts);
      auto pair = names;
      if (pair.second < pair.first)
        std::swap(pair.first, pair.second);
      ++collision_pair_counts_[pair];
      auto & representative_ids = collision_pair_sample_ids_[pair];
      if (representative_ids.size() < 5)
        representative_ids.push_back(sample_id);
      if (scene_ids.count(names.first) != 0 || scene_ids.count(names.second) != 0) {
        sample.scene_collision = true;
      }
    }
    sample.collision_free =
      sample.bounds_valid && !sample.self_collision && !sample.scene_collision;
    return sample;
  }

  [[nodiscard]] std::vector<std::string> worldObjectIds() const
  {
    auto ids = scene_->getWorld()->getObjectIds();
    std::sort(ids.begin(), ids.end());
    return ids;
  }

  moveit::core::RobotModelPtr model_;
  planning_scene::PlanningScenePtr scene_;
  moveit::core::RobotState state_;
  pick_place::SO101Profile profile_;
  CollisionPairCounts collision_pair_counts_;
  CollisionPairSampleIds collision_pair_sample_ids_;
};

WorkspaceEvaluatorBuildResult
WorkspaceStateEvaluator::create(const std::shared_ptr<rclcpp::Node> & node,
                                const pick_place::SO101Profile & profile)
{
  try {
    robot_model_loader::RobotModelLoader::Options options("robot_description");
    options.load_kinematics_solvers = false;
    robot_model_loader::RobotModelLoader loader(node, options);
    auto model = loader.getModel();
    if (!model)
      return failure("model_load_failed", "RobotModelLoader returned no model");
    const auto * group = model->getJointModelGroup(profile.planning_group);
    if (!group || group->getActiveJointModelNames() != profile.arm_joints) {
      return failure("arm_group_mismatch", "arm group does not contain exactly joints 1-5");
    }
    if (!model->hasLinkModel(profile.tcp_link)) {
      return failure("tcp_link_missing", "SO-101 TCP link is missing");
    }
    if (!model->hasJointModel(profile.gripper_joint)) {
      return failure("gripper_joint_missing", "SO-101 q6 joint is missing");
    }
    moveit::core::RobotState bounds_state(model);
    bounds_state.setToDefaultValues();
    bounds_state.setVariablePosition(profile.gripper_joint, profile.q6_preopen);
    if (!bounds_state.satisfiesBounds(model->getJointModel(profile.gripper_joint))) {
      return failure("preopen_out_of_bounds", "canonical q6 preopen violates model bounds");
    }
    return {std::unique_ptr<WorkspaceStateEvaluator>(
              new WorkspaceStateEvaluator(std::make_unique<Impl>(model, profile))),
            std::nullopt};
  } catch (const std::exception & error) {
    return failure("model_load_failed", error.what());
  }
}

WorkspaceStateEvaluator::WorkspaceStateEvaluator(std::unique_ptr<Impl> impl) :
    impl_(std::move(impl))
{
}
WorkspaceStateEvaluator::~WorkspaceStateEvaluator() = default;
WorkspaceStateEvaluator::WorkspaceStateEvaluator(WorkspaceStateEvaluator &&) noexcept = default;
WorkspaceStateEvaluator &
WorkspaceStateEvaluator::operator=(WorkspaceStateEvaluator &&) noexcept = default;

PoseSample WorkspaceStateEvaluator::evaluate(std::uint64_t sample_id,
                                             const GeneratedJointSample & generated)
{
  return impl_->evaluate(sample_id, generated);
}
const CollisionPairCounts & WorkspaceStateEvaluator::collisionPairCounts() const noexcept
{
  return impl_->collision_pair_counts_;
}
const CollisionPairSampleIds & WorkspaceStateEvaluator::collisionPairSampleIds() const noexcept
{
  return impl_->collision_pair_sample_ids_;
}
std::vector<std::string> WorkspaceStateEvaluator::worldObjectIds() const
{
  return impl_->worldObjectIds();
}
double WorkspaceStateEvaluator::gripperPreopen() const noexcept
{
  return impl_->profile_.q6_preopen;
}
}  // namespace so101_gazebo_demo::workspace
