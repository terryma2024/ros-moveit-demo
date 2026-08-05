#include "so101_gazebo_demo/pick_place/so101_moveit_scene_policy.hpp"

namespace so101_gazebo_demo::pick_place
{
namespace adapters = pick_place_common::ros_adapters;

adapters::ScenePreparation SO101MoveItScenePolicy::prepare(adapters::MoveItSceneOperation operation,
                                                           const ExecutionContext & context) const
{
  adapters::ScenePreparation result;
  if (operation == adapters::MoveItSceneOperation::DETACH) {
    result.skip_command = idempotent_ && context.before.fresh &&
                          context.before.moveit_task_object_attached &&
                          !*context.before.moveit_task_object_attached &&
                          !context.before.moveit_task_object_attached_link &&
                          context.before.moveit_task_object_touch_links.empty() &&
                          context.before.moveit_world_object_poses.count(task_object_id_) == 1;
    return result;
  }
  if (!context.before.gazebo_task_object_pose_world) {
    result.failure = ActionResult{
      ActionStatus::FAILED,
      Failure{FailureCategory::MOVEIT_SCENE,
              "GAZEBO_TASK_OBJECT_POSE_MISSING",
              operation == adapters::MoveItSceneOperation::ATTACH
                ? "Cannot attach MoveIt without the settled Gazebo TaskObject pose"
                : "Cannot synchronize MoveIt without an observed Gazebo TaskObject pose",
              {}}};
    return result;
  }
  result.task_object_pose = context.before.gazebo_task_object_pose_world;
  result.upsert_before_attach = operation == adapters::MoveItSceneOperation::ATTACH;
  return result;
}
}  // namespace so101_gazebo_demo::pick_place
