#include "panda_gazebo_demo/pick_place/panda_moveit_scene_policy.hpp"

namespace panda_gazebo_demo::pick_place
{
namespace adapters = pick_place_common::ros_adapters;
namespace
{
bool detachedBoundaryComplete(const WorldSnapshot & snapshot, const GripperLimits & limits)
{
  return snapshot.fresh && snapshot.arm_stationary && snapshot.gazebo_task_object_attached &&
         !*snapshot.gazebo_task_object_attached && snapshot.moveit_task_object_attached &&
         !*snapshot.moveit_task_object_attached && !snapshot.moveit_task_object_attached_link &&
         snapshot.moveit_task_object_touch_links.empty() &&
         snapshot.gazebo_task_object_pose_world && snapshot.gazebo_task_object_stationary &&
         *snapshot.gazebo_task_object_stationary &&
         snapshot.moveit_world_object_poses.count("table") == 1 &&
         snapshot.moveit_world_object_poses.count("coke") == 1 &&
         validateGripperOpen(snapshot, limits).ok;
}
}  // namespace

adapters::ScenePreparation PandaMoveItScenePolicy::prepare(adapters::MoveItSceneOperation operation,
                                                           const ExecutionContext & context) const
{
  adapters::ScenePreparation result;
  if (operation == adapters::MoveItSceneOperation::ATTACH) {
    return result;
  }
  if (operation == adapters::MoveItSceneOperation::DETACH) {
    result.skip_command = idempotent_ && detachedBoundaryComplete(context.before, gripper_limits_);
    return result;
  }
  if (!context.before.gazebo_task_object_pose_world) {
    result.failure =
      ActionResult{ActionStatus::FAILED,
                   Failure{FailureCategory::MOVEIT_SCENE,
                           "GAZEBO_COKE_POSE_MISSING",
                           "Cannot synchronize MoveIt without an observed Gazebo Coke pose",
                           {}}};
    return result;
  }
  result.task_object_pose = context.before.gazebo_task_object_pose_world;
  if (idempotent_ && detachedBoundaryComplete(context.before, gripper_limits_)) {
    const auto & actual = context.before.moveit_world_object_poses.at("coke");
    result.skip_command = positionDistance(actual, *result.task_object_pose) <= 1e-5 &&
                          orientationDistance(actual, *result.task_object_pose) <= 1e-4;
  }
  return result;
}
}  // namespace panda_gazebo_demo::pick_place
