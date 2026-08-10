#include "so101_gazebo_demo/pick_place/moveit_scene_adapter.hpp"

#include <cmath>
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
  return object;
}

geometry_msgs::msg::Pose identityPose()
{
  geometry_msgs::msg::Pose pose;
  pose.orientation.w = 1.0;
  return pose;
}

}  // namespace

moveit_msgs::msg::CollisionObject
makeTaskObjectCollisionObject(const MoveItSceneGeometry & geometry, const Pose3d & pose)
{
  auto object = baseObject(geometry, geometry.task_object_id, pose);
  constexpr double pi = 3.14159265358979323846;
  const double angle_step = 2.0 * pi / geometry.task_object_side_count;
  const double radial_center =
    geometry.task_object_outer_radius - geometry.task_object_wall_thickness / 2.0;
  const double chord = 2.0 * geometry.task_object_outer_radius * std::sin(angle_step / 2.0);
  const double wall_height = geometry.task_object_height - geometry.task_object_bottom_thickness;
  for (int index = 0; index < geometry.task_object_side_count; ++index) {
    const double angle = index * angle_step;
    shape_msgs::msg::SolidPrimitive wall;
    wall.type = shape_msgs::msg::SolidPrimitive::BOX;
    wall.dimensions = {chord, geometry.task_object_wall_thickness, wall_height};
    object.primitives.push_back(wall);
    auto wall_pose = identityPose();
    wall_pose.position.x = radial_center * std::sin(angle);
    wall_pose.position.y = radial_center * std::cos(angle);
    wall_pose.position.z = geometry.task_object_bottom_thickness / 2.0;
    wall_pose.orientation.z = std::sin(-angle / 2.0);
    wall_pose.orientation.w = std::cos(-angle / 2.0);
    object.primitive_poses.push_back(wall_pose);
  }
  shape_msgs::msg::SolidPrimitive bottom;
  bottom.type = shape_msgs::msg::SolidPrimitive::CYLINDER;
  bottom.dimensions.resize(2);
  bottom.dimensions[shape_msgs::msg::SolidPrimitive::CYLINDER_HEIGHT] =
    geometry.task_object_bottom_thickness;
  bottom.dimensions[shape_msgs::msg::SolidPrimitive::CYLINDER_RADIUS] =
    geometry.task_object_outer_radius;
  object.primitives.push_back(bottom);
  auto bottom_pose = identityPose();
  bottom_pose.position.z =
    -geometry.task_object_height / 2.0 + geometry.task_object_bottom_thickness / 2.0;
  object.primitive_poses.push_back(bottom_pose);
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
  object.primitive_poses.push_back(identityPose());
  return object;
}

moveit_msgs::msg::CollisionObject makePedestalCollisionObject(const MoveItSceneGeometry & geometry,
                                                              const Pose3d & pose)
{
  auto object = baseObject(geometry, geometry.pedestal_id, pose);
  shape_msgs::msg::SolidPrimitive primitive;
  primitive.type = shape_msgs::msg::SolidPrimitive::BOX;
  primitive.dimensions.assign(geometry.pedestal_size.begin(), geometry.pedestal_size.end());
  object.primitives.push_back(primitive);
  object.primitive_poses.push_back(identityPose());
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

ActionResult MoveItSceneAdapter::attachTaskObject(const MoveItAttachmentSpec & spec)
{
  if (spec.link_name.empty() || spec.touch_links.empty()) {
    return sceneFailure("MOVEIT_ATTACH_METADATA_INVALID",
                        "MoveIt attach link and touch links must not be empty");
  }
  if (!impl_->move_group.attachObject(impl_->geometry.task_object_id, spec.link_name,
                                      spec.touch_links)) {
    return sceneFailure("MOVEIT_ATTACH_REQUEST_FAILED",
                        "MoveIt rejected the TaskObject attach request");
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ActionResult MoveItSceneAdapter::detachTaskObject()
{
  if (!impl_->move_group.detachObject(impl_->geometry.task_object_id)) {
    return sceneFailure("MOVEIT_DETACH_REQUEST_FAILED",
                        "MoveIt rejected the TaskObject detach request");
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ActionResult MoveItSceneAdapter::upsertTaskObjectWorldPose(const Pose3d & pose)
{
  if (impl_->planning_scene.getAttachedObjects({impl_->geometry.task_object_id})
        .count(impl_->geometry.task_object_id) != 0) {
    return sceneFailure("MOVEIT_UPSERT_OBJECT_ATTACHED",
                        "Cannot upsert TaskObject while it is attached in MoveIt");
  }
  if (!impl_->planning_scene.applyCollisionObject(
        makeTaskObjectCollisionObject(impl_->geometry, pose))) {
    return sceneFailure("MOVEIT_TASK_OBJECT_UPSERT_APPLY_FAILED",
                        "Failed to apply the canonical TaskObject collision object");
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
    {impl_->geometry.task_object_id, impl_->geometry.table_id, impl_->geometry.pedestal_id});
  const auto attached_objects =
    impl_->planning_scene.getAttachedObjects({impl_->geometry.task_object_id});

  MoveItSceneState state;
  const auto task_object = objects.find(impl_->geometry.task_object_id);
  state.task_object_in_world = task_object != objects.end();
  if (state.task_object_in_world) {
    state.task_object_world_pose = fromMessage(task_object->second.pose);
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
  const auto attached = attached_objects.find(impl_->geometry.task_object_id);
  state.task_object_attached = attached != attached_objects.end();
  if (state.task_object_attached) {
    state.attached_link = attached->second.link_name;
    state.touch_links = attached->second.touch_links;
  }
  return state;
}

}  // namespace so101_gazebo_demo::pick_place
