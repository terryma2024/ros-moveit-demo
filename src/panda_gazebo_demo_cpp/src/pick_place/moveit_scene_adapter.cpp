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
  return {ActionStatus::FAILED,
          Failure{FailureCategory::MOVEIT_SCENE, std::move(code), std::move(message), {}}};
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
  Impl(const std::shared_ptr<rclcpp::Node> & node, const std::string & planning_group,
       std::string object_id) : move_group(node, planning_group), object_id(std::move(object_id))
  {
  }

  moveit::planning_interface::MoveGroupInterface move_group;
  moveit::planning_interface::PlanningSceneInterface planning_scene;
  std::string object_id;
  const std::string table_id{"table"};
};

MoveItSceneAdapter::MoveItSceneAdapter(const std::shared_ptr<rclcpp::Node> & node,
                                       const std::string & planning_group, std::string object_id) :
    impl_(std::make_unique<Impl>(node, planning_group, std::move(object_id)))
{
}

MoveItSceneAdapter::~MoveItSceneAdapter() = default;

ActionResult MoveItSceneAdapter::attachTaskObject(const MoveItAttachmentSpec & spec)
{
  if (!impl_->move_group.attachObject(impl_->object_id, spec.link_name, spec.touch_links)) {
    return sceneFailure("MOVEIT_ATTACH_REQUEST_FAILED", "MoveIt rejected the Coke attach request");
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ActionResult MoveItSceneAdapter::detachTaskObject()
{
  if (!impl_->move_group.detachObject(impl_->object_id)) {
    return sceneFailure("MOVEIT_DETACH_REQUEST_FAILED", "MoveIt rejected the Coke detach request");
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ActionResult MoveItSceneAdapter::upsertTaskObjectWorldPose(const Pose3d & pose)
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

ActionResult MoveItSceneAdapter::upsertTableWorldPose(const Pose3d & pose)
{
  auto objects = impl_->planning_scene.getObjects({impl_->table_id});
  const auto existing = objects.find(impl_->table_id);
  moveit_msgs::msg::CollisionObject upserted;
  if (existing != objects.end()) {
    upserted = existing->second;
  } else {
    upserted.id = impl_->table_id;
    shape_msgs::msg::SolidPrimitive primitive;
    primitive.type = shape_msgs::msg::SolidPrimitive::BOX;
    primitive.dimensions = {1.2, 0.8, 0.05};
    upserted.primitives.push_back(primitive);
    geometry_msgs::msg::Pose local_pose;
    local_pose.orientation.w = 1.0;
    upserted.primitive_poses.push_back(local_pose);
  }
  upserted.header.frame_id = "world";
  upserted.pose = toMessage(pose);
  upserted.operation = moveit_msgs::msg::CollisionObject::ADD;
  if (!impl_->planning_scene.applyCollisionObject(upserted)) {
    return sceneFailure("MOVEIT_TABLE_UPSERT_APPLY_FAILED",
                        "Failed to apply the canonical table world pose");
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

std::optional<MoveItSceneState> MoveItSceneAdapter::observe()
{
  const auto objects = impl_->planning_scene.getObjects({impl_->object_id, impl_->table_id});
  const auto attached_objects = impl_->planning_scene.getAttachedObjects({impl_->object_id});

  MoveItSceneState state;
  const auto world = objects.find(impl_->object_id);
  state.task_object_in_world = world != objects.end();
  if (state.task_object_in_world) {
    state.task_object_world_pose = worldPoseFromCollisionObject(world->second);
  }
  const auto table = objects.find(impl_->table_id);
  state.table_in_world = table != objects.end();
  if (state.table_in_world) {
    state.table_world_pose = worldPoseFromCollisionObject(table->second);
  }

  const auto attached = attached_objects.find(impl_->object_id);
  state.task_object_attached = attached != attached_objects.end();
  if (state.task_object_attached) {
    state.attached_link = attached->second.link_name;
    state.touch_links = {attached->second.touch_links.begin(), attached->second.touch_links.end()};
  }
  return state;
}

}  // namespace panda_gazebo_demo::pick_place
