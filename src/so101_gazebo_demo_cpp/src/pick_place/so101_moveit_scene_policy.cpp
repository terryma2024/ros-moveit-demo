#include "so101_gazebo_demo/pick_place/so101_moveit_scene_policy.hpp"

#include <mutex>
#include <variant>

#include "so101_gazebo_demo/pick_place/so101_attachment_contracts.hpp"

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
  if (operation == adapters::MoveItSceneOperation::SYNC && final_evidence_) {
    const auto frozen = final_evidence_->frozen();
    if (!frozen || !frozen->evaluation.stable || !frozen->evaluation.evidence) {
      result.failure = ActionResult{
        ActionStatus::FAILED,
        Failure{FailureCategory::MOVEIT_SCENE,
                "FINAL_PLACEMENT_EVIDENCE_NOT_FROZEN",
                "MoveIt final world synchronization requires successful frozen physical evidence",
                {}}};
      return result;
    }
    result.task_object_pose = frozen->evaluation.evidence->final_pose;
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
  if (operation == adapters::MoveItSceneOperation::ATTACH) {
    const auto derived = derivePlanningShadowPose(context.before);
    if (std::holds_alternative<Failure>(derived)) {
      result.failure = ActionResult{ActionStatus::FAILED, std::get<Failure>(derived)};
      result.task_object_pose.reset();
      result.upsert_before_attach = false;
      return result;
    }
    const std::scoped_lock lock(mutex_);
    attached_shadow_relative_pose_ = std::get<Pose3d>(derived);
  }
  return result;
}

std::optional<Pose3d> SO101MoveItScenePolicy::attachedShadowRelativePose() const
{
  const std::scoped_lock lock(mutex_);
  return attached_shadow_relative_pose_;
}
}  // namespace so101_gazebo_demo::pick_place
