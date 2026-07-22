#include "panda_gazebo_demo/pick_place/moveit_scene_executor.hpp"

#include <chrono>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace panda_gazebo_demo::pick_place
{
namespace
{

constexpr char kCokeObjectId[] = "coke";
constexpr char kAttachLink[] = "panda_hand";
const std::vector<std::string> kTouchLinks{
  "panda_hand", "panda_leftfinger", "panda_rightfinger"};
const std::set<std::string> kTouchLinkSet(kTouchLinks.begin(), kTouchLinks.end());

ActionResult sceneFailure(
  ActionStatus status, std::string code, std::string message,
  std::map<std::string, double> metrics = {})
{
  return {status, Failure{FailureCategory::MOVEIT_SCENE, std::move(code),
      std::move(message), std::move(metrics)}};
}

bool validConfiguration(const MoveItSceneConfig & config) noexcept
{
  switch (config.operation) {
    case MoveItSceneOperation::ATTACH:
      return config.state == State::ATTACH_MOVEIT;
    case MoveItSceneOperation::DETACH:
      return config.state == State::DETACH_MOVEIT ||
             config.state == State::RECOVER_DETACH_MOVEIT;
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

MoveItSceneExecutor::MoveItSceneExecutor(
  std::shared_ptr<IMoveItSceneAdapter> adapter, MoveItSceneConfig config,
  double timeout_seconds, double poll_interval_seconds)
: adapter_(std::move(adapter)), config_(config), timeout_seconds_(timeout_seconds),
  poll_interval_seconds_(poll_interval_seconds)
{
}

ActionResult MoveItSceneExecutor::execute(const ExecutionContext & context)
{
  if (context.state != config_.state || !validConfiguration(config_)) {
    return sceneFailure(ActionStatus::NOT_SUPPORTED, "STATE_NOT_EXECUTABLE",
      std::string("MoveIt scene executor configured for ") + toString(config_.state) +
      " cannot execute " + toString(context.state));
  }
  if (!adapter_) {
    return sceneFailure(ActionStatus::FAILED, "MOVEIT_SCENE_ADAPTER_MISSING",
      "MoveIt scene adapter is not configured");
  }
  if (timeout_seconds_ <= 0.0 || poll_interval_seconds_ <= 0.0) {
    return sceneFailure(ActionStatus::FAILED, "MOVEIT_SCENE_TIMING_INVALID",
      "MoveIt scene timeout and polling interval must be positive");
  }

  {
    std::lock_guard<std::mutex> lock(mutex_);
    cancel_requested_ = false;
  }

  ActionResult command_result;
  std::optional<Pose3d> synchronized_pose;
  switch (config_.operation) {
    case MoveItSceneOperation::ATTACH:
      command_result = adapter_->attachCoke(kAttachLink, kTouchLinks);
      break;
    case MoveItSceneOperation::DETACH:
      if (config_.idempotent && context.before.moveit_coke_attached &&
        !*context.before.moveit_coke_attached &&
        context.before.moveit_world_object_poses.count(kCokeObjectId) == 1)
      {
        return {ActionStatus::SUCCEEDED, std::nullopt};
      }
      command_result = adapter_->detachCoke();
      break;
    case MoveItSceneOperation::SYNC:
      if (!context.before.gazebo_coke_pose_world) {
        return sceneFailure(ActionStatus::FAILED, "GAZEBO_COKE_POSE_MISSING",
          "Cannot synchronize MoveIt without an observed Gazebo Coke pose");
      }
      synchronized_pose = context.before.gazebo_coke_pose_world;
      command_result = adapter_->syncCokeWorldPose(*synchronized_pose);
      break;
  }

  if (command_result.status != ActionStatus::SUCCEEDED) {
    return command_result;
  }
  return waitForConvergence(synchronized_pose);
}

ActionResult MoveItSceneExecutor::waitForConvergence(
  const std::optional<Pose3d> & synchronized_pose)
{
  const auto deadline = std::chrono::steady_clock::now() +
    std::chrono::duration<double>(timeout_seconds_);
  const auto poll_interval = std::chrono::duration<double>(poll_interval_seconds_);
  std::size_t observation_count = 0;

  while (std::chrono::steady_clock::now() < deadline) {
    {
      std::lock_guard<std::mutex> lock(mutex_);
      if (cancel_requested_) {
        return sceneFailure(ActionStatus::CANCELLED, "MOVEIT_SCENE_CANCELLED",
          "MoveIt scene convergence wait was cancelled");
      }
    }

    const auto state = adapter_->observe();
    ++observation_count;
    if (state) {
      bool converged = false;
      switch (config_.operation) {
        case MoveItSceneOperation::ATTACH:
          converged = state->coke_attached && !state->coke_in_world &&
            state->attached_link == kAttachLink && state->touch_links == kTouchLinkSet;
          break;
        case MoveItSceneOperation::DETACH:
          converged = !state->coke_attached && state->coke_in_world;
          break;
        case MoveItSceneOperation::SYNC:
          converged = !state->coke_attached && state->coke_in_world &&
            synchronized_pose && state->coke_world_pose &&
            poseMatches(*state->coke_world_pose, *synchronized_pose);
          break;
      }
      if (converged) {
        return {ActionStatus::SUCCEEDED, std::nullopt};
      }
    }

    std::unique_lock<std::mutex> lock(mutex_);
    condition_.wait_for(lock, poll_interval, [this]() {return cancel_requested_;});
  }

  return sceneFailure(ActionStatus::TIMED_OUT, "MOVEIT_SCENE_CONVERGENCE_TIMEOUT",
    "MoveIt Planning Scene did not converge to the requested state",
           {{"observation_count", static_cast<double>(observation_count)}});
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

}  // namespace panda_gazebo_demo::pick_place
