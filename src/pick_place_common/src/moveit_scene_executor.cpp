#include "pick_place_common/moveit_scene_executor.hpp"

#include <chrono>
#include <cmath>
#include <map>
#include <utility>

namespace pick_place_common::ros_adapters
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
  if (config.task_object_id.empty()) {
    return false;
  }
  switch (config.operation) {
    case MoveItSceneOperation::ATTACH:
      return config.state == State::ATTACH_MOVEIT && !config.attachment.link_name.empty();
    case MoveItSceneOperation::DETACH:
      return config.state == State::DETACH_MOVEIT || config.state == State::RECOVER_DETACH_MOVEIT;
    case MoveItSceneOperation::SYNC:
      return config.state == State::SYNC_WORLD_OBJECT ||
             config.state == State::RECOVER_SYNC_WORLD_OBJECT;
  }
  return false;
}

bool poseMatches(const Pose3d & actual, const Pose3d & expected) noexcept
{
  return positionDistance(actual, expected) <= 1e-5 &&
         orientationDistance(actual, expected) <= 1e-4;
}
}  // namespace

MoveItSceneExecutor::MoveItSceneExecutor(std::shared_ptr<IMoveItSceneAdapter> adapter,
                                         MoveItSceneConfig config,
                                         std::shared_ptr<const IMoveItScenePolicy> policy) :
    adapter_(std::move(adapter)), config_(std::move(config)), policy_(std::move(policy))
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
  if (!policy_) {
    return sceneFailure(ActionStatus::FAILED, "MOVEIT_SCENE_POLICY_MISSING",
                        "MoveIt scene policy is not configured");
  }
  if (!std::isfinite(config_.timeout_seconds) || !std::isfinite(config_.poll_interval_seconds) ||
      config_.timeout_seconds <= 0.0 || config_.poll_interval_seconds <= 0.0) {
    return sceneFailure(ActionStatus::FAILED, "MOVEIT_SCENE_TIMING_INVALID",
                        "MoveIt scene timeout and poll interval must be finite and positive");
  }
  {
    std::lock_guard<std::mutex> lock(mutex_);
    cancel_requested_ = false;
  }

  const auto preparation = policy_->prepare(config_.operation, context);
  if (preparation.failure) {
    return *preparation.failure;
  }
  if (preparation.skip_command) {
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }

  ActionResult command;
  switch (config_.operation) {
    case MoveItSceneOperation::ATTACH:
      if (preparation.upsert_before_attach) {
        if (!preparation.task_object_pose) {
          return sceneFailure(ActionStatus::FAILED, "MOVEIT_SCENE_PREPARATION_INVALID",
                              "Attach preparation requested upsert without a task-object pose");
        }
        command = adapter_->upsertTaskObjectWorldPose(*preparation.task_object_pose);
        if (command.status != ActionStatus::SUCCEEDED) {
          return command;
        }
      }
      command = adapter_->attachTaskObject(config_.attachment);
      break;
    case MoveItSceneOperation::DETACH:
      command = adapter_->detachTaskObject();
      break;
    case MoveItSceneOperation::SYNC:
      if (!preparation.task_object_pose) {
        return sceneFailure(ActionStatus::FAILED, "MOVEIT_SCENE_PREPARATION_INVALID",
                            "Sync preparation did not provide a task-object pose");
      }
      command = adapter_->upsertTaskObjectWorldPose(*preparation.task_object_pose);
      break;
  }
  if (command.status != ActionStatus::SUCCEEDED) {
    return command;
  }
  return waitForConvergence(preparation.task_object_pose);
}

ActionResult MoveItSceneExecutor::waitForConvergence(const std::optional<Pose3d> & pose)
{
  const auto deadline =
    std::chrono::steady_clock::now() + std::chrono::duration<double>(config_.timeout_seconds);
  const auto interval = std::chrono::duration<double>(config_.poll_interval_seconds);
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
                      state->attached_link == config_.attachment.link_name &&
                      state->touch_links == config_.attachment.touch_links;
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
}  // namespace pick_place_common::ros_adapters
