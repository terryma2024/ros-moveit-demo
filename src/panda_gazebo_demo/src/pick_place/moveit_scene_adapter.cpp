#include "panda_gazebo_demo/pick_place/moveit_scene_adapter.hpp"

#include <map>
#include <memory>
#include <optional>
#include <set>
#include <string>
#include <utility>
#include <vector>

#include <moveit/move_group_interface/move_group_interface.hpp>
#include <moveit/planning_scene_interface/planning_scene_interface.hpp>
#include <moveit_msgs/msg/collision_object.hpp>
#include <rclcpp/node.hpp>
#include <shape_msgs/msg/solid_primitive.hpp>

#include "panda_gazebo_demo/pick_place/moveit_world_object_pose.hpp"

namespace panda_gazebo_demo::pick_place
{
namespace
{

ActionResult sceneFailure(std::string code, std::string message)
{
  return {ActionStatus::FAILED, Failure{FailureCategory::MOVEIT_SCENE, std::move(code),
      std::move(message), {}}};
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

}  // namespace

class MoveItSceneAdapter::Impl
{
public:
  Impl(
    std::shared_ptr<rclcpp::Node> node, const std::string & planning_group,
    std::string object_id)
  : move_group(std::move(node), planning_group), object_id(std::move(object_id))
  {
  }

  moveit::planning_interface::MoveGroupInterface move_group;
  moveit::planning_interface::PlanningSceneInterface planning_scene;
  std::string object_id;
};

MoveItSceneAdapter::MoveItSceneAdapter(
  std::shared_ptr<rclcpp::Node> node, std::string planning_group,
  std::string object_id)
: impl_(std::make_unique<Impl>(std::move(node), planning_group, std::move(object_id)))
{
}

MoveItSceneAdapter::~MoveItSceneAdapter() = default;

ActionResult MoveItSceneAdapter::attachCoke(
  const std::string & link_name, const std::vector<std::string> & touch_links)
{
  if (!impl_->move_group.attachObject(impl_->object_id, link_name, touch_links)) {
    return sceneFailure("MOVEIT_ATTACH_REQUEST_FAILED",
      "MoveIt rejected the Coke attach request");
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ActionResult MoveItSceneAdapter::detachCoke()
{
  if (!impl_->move_group.detachObject(impl_->object_id)) {
    return sceneFailure("MOVEIT_DETACH_REQUEST_FAILED",
      "MoveIt rejected the Coke detach request");
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ActionResult MoveItSceneAdapter::syncCokeWorldPose(const Pose3d & pose)
{
  if (impl_->planning_scene.getAttachedObjects({impl_->object_id}).count(impl_->object_id) != 0) {
    return sceneFailure("MOVEIT_SYNC_OBJECT_ATTACHED",
      "Cannot synchronize Coke while it is attached in MoveIt");
  }

  auto objects = impl_->planning_scene.getObjects({impl_->object_id});
  const auto existing = objects.find(impl_->object_id);
  if (existing == objects.end()) {
    return sceneFailure("MOVEIT_SYNC_OBJECT_MISSING",
      "Cannot synchronize a Coke object that is absent from the MoveIt world");
  }

  auto synchronized = existing->second;
  synchronized.header.frame_id = "world";
  synchronized.pose = toMessage(pose);
  synchronized.operation = moveit_msgs::msg::CollisionObject::ADD;
  if (!impl_->planning_scene.applyCollisionObject(synchronized)) {
    return sceneFailure("MOVEIT_SYNC_APPLY_FAILED",
      "Failed to apply the synchronized Coke world pose");
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ActionResult MoveItSceneAdapter::upsertCokeWorldPose(const Pose3d & pose)
{
  if (impl_->planning_scene.getAttachedObjects({impl_->object_id}).count(impl_->object_id) != 0) {
    return sceneFailure("MOVEIT_UPSERT_OBJECT_ATTACHED",
      "Cannot upsert Coke while it is attached in MoveIt");
  }

  auto objects = impl_->planning_scene.getObjects({impl_->object_id});
  const auto existing = objects.find(impl_->object_id);
  moveit_msgs::msg::CollisionObject upserted;
  if (existing != objects.end()) {
    upserted = existing->second;
  } else {
    upserted.id = impl_->object_id;
    shape_msgs::msg::SolidPrimitive primitive;
    primitive.type = shape_msgs::msg::SolidPrimitive::CYLINDER;
    primitive.dimensions.resize(2);
    primitive.dimensions[shape_msgs::msg::SolidPrimitive::CYLINDER_HEIGHT] = 0.122;
    primitive.dimensions[shape_msgs::msg::SolidPrimitive::CYLINDER_RADIUS] = 0.033;
    upserted.primitives.push_back(primitive);
    geometry_msgs::msg::Pose local_pose;
    local_pose.orientation.w = 1.0;
    upserted.primitive_poses.push_back(local_pose);
  }
  upserted.header.frame_id = "world";
  upserted.pose = toMessage(pose);
  upserted.operation = moveit_msgs::msg::CollisionObject::ADD;
  if (!impl_->planning_scene.applyCollisionObject(upserted)) {
    return sceneFailure("MOVEIT_UPSERT_APPLY_FAILED",
      "Failed to apply the canonical Coke world pose");
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

std::optional<MoveItSceneState> MoveItSceneAdapter::observe()
{
  const auto objects = impl_->planning_scene.getObjects({impl_->object_id});
  const auto attached_objects =
    impl_->planning_scene.getAttachedObjects({impl_->object_id});

  MoveItSceneState state;
  const auto world = objects.find(impl_->object_id);
  state.coke_in_world = world != objects.end();
  if (state.coke_in_world) {
    state.coke_world_pose = worldPoseFromCollisionObject(world->second);
  }

  const auto attached = attached_objects.find(impl_->object_id);
  state.coke_attached = attached != attached_objects.end();
  if (state.coke_attached) {
    state.attached_link = attached->second.link_name;
    state.touch_links = {
      attached->second.touch_links.begin(), attached->second.touch_links.end()};
  }
  return state;
}

}  // namespace panda_gazebo_demo::pick_place
