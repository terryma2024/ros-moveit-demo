#include "so101_gazebo_demo/pick_place/moveit_scene_executor.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <map>
#include <optional>
#include <string>
#include <utility>

namespace so101_gazebo_demo::pick_place
{
namespace
{

ActionResult sceneFailure(ActionStatus status, std::string code, std::string message,
                          std::map<std::string, double> metrics = {})
{
  return {status, Failure{FailureCategory::MOVEIT_SCENE, std::move(code), std::move(message),
                          std::move(metrics)}};
}

bool validConfiguration(const MoveItSceneConfig & config) noexcept
{
  if (config.task_object_id.empty())
    return false;
  switch (config.operation) {
    case MoveItSceneOperation::ATTACH:
      return config.state == State::ATTACH_MOVEIT;
    case MoveItSceneOperation::DETACH:
      return config.state == State::DETACH_MOVEIT || config.state == State::RECOVER_DETACH_MOVEIT;
    case MoveItSceneOperation::SYNC:
      return config.state == State::SYNC_WORLD_OBJECT ||
             config.state == State::RECOVER_SYNC_WORLD_OBJECT;
  }
  return false;
}

double localPositionDistance(const Pose3d & a, const Pose3d & b)
{
  return std::hypot(std::hypot(a.x - b.x, a.y - b.y), a.z - b.z);
}

double localOrientationDistance(const Pose3d & a, const Pose3d & b)
{
  const auto a_norm = std::hypot(std::hypot(a.qx, a.qy), std::hypot(a.qz, a.qw));
  const auto b_norm = std::hypot(std::hypot(b.qx, b.qy), std::hypot(b.qz, b.qw));
  if (a_norm <= 1e-12 || b_norm <= 1e-12) {
    return INFINITY;
  }
  const auto dot =
    std::abs((a.qx * b.qx + a.qy * b.qy + a.qz * b.qz + a.qw * b.qw) / (a_norm * b_norm));
  return 2.0 * std::acos(std::clamp(dot, 0.0, 1.0));
}

bool poseMatches(const Pose3d & actual, const Pose3d & expected)
{
  return localPositionDistance(actual, expected) <= 1e-5 &&
         localOrientationDistance(actual, expected) <= 1e-4;
}

}  // namespace

MoveItSceneExecutor::MoveItSceneExecutor(std::shared_ptr<IMoveItSceneAdapter> adapter,
                                         MoveItSceneConfig config, MoveItAttachmentSpec attachment,
                                         double timeout_seconds, double poll_interval_seconds) :
    adapter_(std::move(adapter)), config_(std::move(config)), attachment_(std::move(attachment)),
    timeout_seconds_(timeout_seconds), poll_interval_seconds_(poll_interval_seconds)
{
}

ActionResult MoveItSceneExecutor::execute(const ExecutionContext & context)
{
  if (context.state != config_.state || !validConfiguration(config_)) {
    return sceneFailure(ActionStatus::NOT_SUPPORTED, "STATE_NOT_EXECUTABLE",
                        "MoveIt scene executor is not configured for the requested state");
  }
  if (!adapter_) {
    return sceneFailure(ActionStatus::FAILED, "MOVEIT_SCENE_ADAPTER_MISSING",
                        "MoveIt scene adapter is not configured");
  }
  if (!std::isfinite(timeout_seconds_) || !std::isfinite(poll_interval_seconds_) ||
      timeout_seconds_ <= 0.0 || poll_interval_seconds_ <= 0.0) {
    return sceneFailure(ActionStatus::FAILED, "MOVEIT_SCENE_TIMING_INVALID",
                        "MoveIt scene timeout and poll interval must be finite and positive");
  }
  {
    std::lock_guard<std::mutex> lock(mutex_);
    cancel_requested_ = false;
  }

  ActionResult command;
  std::optional<Pose3d> pose;
  switch (config_.operation) {
    case MoveItSceneOperation::ATTACH:
      if (!context.before.gazebo_task_object_pose_world) {
        return sceneFailure(ActionStatus::FAILED, "GAZEBO_TASK_OBJECT_POSE_MISSING",
                            "Cannot attach MoveIt without the settled Gazebo TaskObject pose");
      }
      pose = context.before.gazebo_task_object_pose_world;
      command = adapter_->upsertTaskObjectWorldPose(*pose);
      if (command.status != ActionStatus::SUCCEEDED)
        return command;
      command = adapter_->attachTaskObject(attachment_);
      break;
    case MoveItSceneOperation::DETACH:
      if (config_.idempotent && context.before.fresh &&
          context.before.moveit_task_object_attached &&
          !*context.before.moveit_task_object_attached &&
          !context.before.moveit_task_object_attached_link &&
          context.before.moveit_task_object_touch_links.empty() &&
          context.before.moveit_world_object_poses.count(config_.task_object_id) == 1) {
        return {ActionStatus::SUCCEEDED, std::nullopt};
      }
      command = adapter_->detachTaskObject();
      break;
    case MoveItSceneOperation::SYNC:
      if (!context.before.gazebo_task_object_pose_world) {
        return sceneFailure(ActionStatus::FAILED, "GAZEBO_TASK_OBJECT_POSE_MISSING",
                            "Cannot synchronize MoveIt without an observed Gazebo TaskObject pose");
      }
      pose = context.before.gazebo_task_object_pose_world;
      command = adapter_->upsertTaskObjectWorldPose(*pose);
      break;
  }
  if (command.status != ActionStatus::SUCCEEDED) {
    return command;
  }
  return waitForConvergence(pose);
}

ActionResult MoveItSceneExecutor::waitForConvergence(const std::optional<Pose3d> & pose)
{
  const auto deadline =
    std::chrono::steady_clock::now() + std::chrono::duration<double>(timeout_seconds_);
  const auto interval = std::chrono::duration<double>(poll_interval_seconds_);
  std::size_t observations = 0;
  while (std::chrono::steady_clock::now() < deadline) {
    {
      std::lock_guard<std::mutex> lock(mutex_);
      if (cancel_requested_) {
        return sceneFailure(ActionStatus::CANCELLED, "MOVEIT_SCENE_CANCELLED",
                            "MoveIt scene convergence wait was cancelled");
      }
    }
    const auto state = adapter_->observe();
    ++observations;
    if (state) {
      bool converged = false;
      switch (config_.operation) {
        case MoveItSceneOperation::ATTACH:
          converged = state->task_object_attached && !state->task_object_in_world &&
                      state->attached_link == attachment_.link_name &&
                      state->touch_links == attachment_.touch_links;
          break;
        case MoveItSceneOperation::DETACH:
          converged = !state->task_object_attached && state->task_object_in_world &&
                      state->attached_link.empty() && state->touch_links.empty();
          break;
        case MoveItSceneOperation::SYNC:
          converged = !state->task_object_attached && state->task_object_in_world && pose &&
                      state->task_object_world_pose &&
                      poseMatches(*state->task_object_world_pose, *pose);
          break;
      }
      if (converged) {
        return {ActionStatus::SUCCEEDED, std::nullopt};
      }
    }
    std::unique_lock<std::mutex> lock(mutex_);
    condition_.wait_for(lock, interval, [this]() { return cancel_requested_; });
  }
  return sceneFailure(ActionStatus::TIMED_OUT, "MOVEIT_SCENE_CONVERGENCE_TIMEOUT",
                      "MoveIt Planning Scene did not converge to the requested state",
                      {{"observation_count", static_cast<double>(observations)}});
}

ActionResult MoveItSceneExecutor::cancel()
{
  {
    std::lock_guard<std::mutex> lock(mutex_);
    cancel_requested_ = true;
  }
  condition_.notify_all();
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

}  // namespace so101_gazebo_demo::pick_place
