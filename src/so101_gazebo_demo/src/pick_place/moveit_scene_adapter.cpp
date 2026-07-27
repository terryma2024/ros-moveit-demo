#include "so101_gazebo_demo/pick_place/moveit_scene_adapter.hpp"

#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include <moveit/move_group_interface/move_group_interface.hpp>
#include <moveit/planning_scene_interface/planning_scene_interface.hpp>
#include <rclcpp/node.hpp>
#include <shape_msgs/msg/solid_primitive.hpp>

namespace so101_gazebo_demo::pick_place
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

Pose3d fromMessage(const geometry_msgs::msg::Pose & pose)
{
  return {pose.position.x,    pose.position.y,    pose.position.z,   pose.orientation.x,
          pose.orientation.y, pose.orientation.z, pose.orientation.w};
}

moveit_msgs::msg::CollisionObject baseObject(const MoveItSceneGeometry & geometry,
                                             const std::string & id, const Pose3d & pose)
{
  moveit_msgs::msg::CollisionObject object;
  object.header.frame_id = geometry.world_frame;
  object.id = id;
  object.pose = toMessage(pose);
  object.operation = moveit_msgs::msg::CollisionObject::ADD;
  geometry_msgs::msg::Pose local_pose;
  local_pose.orientation.w = 1.0;
  object.primitive_poses.push_back(local_pose);
  return object;
}

}  // namespace

moveit_msgs::msg::CollisionObject makeCokeCollisionObject(const MoveItSceneGeometry & geometry,
                                                          const Pose3d & pose)
{
  auto object = baseObject(geometry, geometry.coke_id, pose);
  shape_msgs::msg::SolidPrimitive primitive;
  primitive.type = shape_msgs::msg::SolidPrimitive::CYLINDER;
  primitive.dimensions.resize(2);
  primitive.dimensions[shape_msgs::msg::SolidPrimitive::CYLINDER_HEIGHT] = geometry.coke_height;
  primitive.dimensions[shape_msgs::msg::SolidPrimitive::CYLINDER_RADIUS] = geometry.coke_radius;
  object.primitives.push_back(primitive);
  return object;
}

moveit_msgs::msg::CollisionObject makeTableCollisionObject(const MoveItSceneGeometry & geometry,
                                                           const Pose3d & pose)
{
  auto object = baseObject(geometry, geometry.table_id, pose);
  shape_msgs::msg::SolidPrimitive primitive;
  primitive.type = shape_msgs::msg::SolidPrimitive::BOX;
  primitive.dimensions.assign(geometry.table_size.begin(), geometry.table_size.end());
  object.primitives.push_back(primitive);
  return object;
}

moveit_msgs::msg::CollisionObject makePedestalCollisionObject(
  const MoveItSceneGeometry & geometry, const Pose3d & pose)
{
  auto object = baseObject(geometry, geometry.pedestal_id, pose);
  shape_msgs::msg::SolidPrimitive primitive;
  primitive.type = shape_msgs::msg::SolidPrimitive::BOX;
  primitive.dimensions.assign(geometry.pedestal_size.begin(), geometry.pedestal_size.end());
  object.primitives.push_back(primitive);
  return object;
}

class MoveItSceneAdapter::Impl
{
public:
  Impl(const std::shared_ptr<rclcpp::Node> & node, const std::string & planning_group,
       MoveItSceneGeometry scene_geometry) :
      move_group(node, planning_group), geometry(std::move(scene_geometry))
  {
  }

  moveit::planning_interface::MoveGroupInterface move_group;
  moveit::planning_interface::PlanningSceneInterface planning_scene;
  MoveItSceneGeometry geometry;
};

MoveItSceneAdapter::MoveItSceneAdapter(const std::shared_ptr<rclcpp::Node> & node,
                                       const std::string & planning_group,
                                       MoveItSceneGeometry geometry) :
    impl_(std::make_unique<Impl>(node, planning_group, std::move(geometry)))
{
}

MoveItSceneAdapter::~MoveItSceneAdapter() = default;

ActionResult MoveItSceneAdapter::attachCoke(const MoveItAttachmentSpec & spec)
{
  if (spec.link_name.empty() || spec.touch_links.empty()) {
    return sceneFailure("MOVEIT_ATTACH_METADATA_INVALID",
                        "MoveIt attach link and touch links must not be empty");
  }
  if (!impl_->move_group.attachObject(impl_->geometry.coke_id, spec.link_name, spec.touch_links)) {
    return sceneFailure("MOVEIT_ATTACH_REQUEST_FAILED", "MoveIt rejected the Coke attach request");
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ActionResult MoveItSceneAdapter::detachCoke()
{
  if (!impl_->move_group.detachObject(impl_->geometry.coke_id)) {
    return sceneFailure("MOVEIT_DETACH_REQUEST_FAILED", "MoveIt rejected the Coke detach request");
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ActionResult MoveItSceneAdapter::upsertCokeWorldPose(const Pose3d & pose)
{
  if (impl_->planning_scene.getAttachedObjects({impl_->geometry.coke_id})
        .count(impl_->geometry.coke_id) != 0) {
    return sceneFailure("MOVEIT_UPSERT_OBJECT_ATTACHED",
                        "Cannot upsert Coke while it is attached in MoveIt");
  }
  if (!impl_->planning_scene.applyCollisionObject(makeCokeCollisionObject(impl_->geometry, pose))) {
    return sceneFailure("MOVEIT_COKE_UPSERT_APPLY_FAILED",
                        "Failed to apply the canonical Coke collision object");
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ActionResult MoveItSceneAdapter::upsertTableWorldPose(const Pose3d & pose)
{
  if (!impl_->planning_scene.applyCollisionObject(
        makeTableCollisionObject(impl_->geometry, pose))) {
    return sceneFailure("MOVEIT_TABLE_UPSERT_APPLY_FAILED",
                        "Failed to apply the canonical table collision object");
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ActionResult MoveItSceneAdapter::upsertPedestalWorldPose(const Pose3d & pose)
{
  if (!impl_->planning_scene.applyCollisionObject(
        makePedestalCollisionObject(impl_->geometry, pose))) {
    return sceneFailure("MOVEIT_PEDESTAL_UPSERT_APPLY_FAILED",
                        "Failed to apply the canonical pedestal collision object");
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

std::optional<MoveItSceneState> MoveItSceneAdapter::observe()
{
  const auto objects = impl_->planning_scene.getObjects(
    {impl_->geometry.coke_id, impl_->geometry.table_id, impl_->geometry.pedestal_id});
  const auto attached_objects = impl_->planning_scene.getAttachedObjects({impl_->geometry.coke_id});

  MoveItSceneState state;
  const auto coke = objects.find(impl_->geometry.coke_id);
  state.coke_in_world = coke != objects.end();
  if (state.coke_in_world) {
    state.coke_world_pose = fromMessage(coke->second.pose);
  }
  const auto table = objects.find(impl_->geometry.table_id);
  state.table_in_world = table != objects.end();
  if (state.table_in_world) {
    state.table_world_pose = fromMessage(table->second.pose);
  }
  const auto pedestal = objects.find(impl_->geometry.pedestal_id);
  state.pedestal_in_world = pedestal != objects.end();
  if (state.pedestal_in_world) {
    state.pedestal_world_pose = fromMessage(pedestal->second.pose);
  }
  const auto attached = attached_objects.find(impl_->geometry.coke_id);
  state.coke_attached = attached != attached_objects.end();
  if (state.coke_attached) {
    state.attached_link = attached->second.link_name;
    state.touch_links = attached->second.touch_links;
  }
  return state;
}

}  // namespace so101_gazebo_demo::pick_place
