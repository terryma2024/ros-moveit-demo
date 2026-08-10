#include "panda_gazebo_demo/pick_place/moveit_world_resetter.hpp"

#include <chrono>
#include <cmath>
#include <string>
#include <thread>
#include <utility>

namespace panda_gazebo_demo::pick_place
{
namespace
{

ActionResult resetFailure(ActionStatus status, std::string code, std::string message)
{
  return {status, Failure{FailureCategory::MOVEIT_SCENE, std::move(code), std::move(message), {}}};
}

bool validPose(const Pose3d & pose)
{
  return std::isfinite(positionDistance(pose, pose)) &&
         std::isfinite(orientationDistance(pose, pose));
}

bool poseMatches(const Pose3d & actual, const Pose3d & expected)
{
  return positionDistance(actual, expected) <= 1e-5 &&
         orientationDistance(actual, expected) <= 1e-4;
}

constexpr Pose3d kCanonicalTablePose{0.0, 0.0, 0.75, 0.0, 0.0, 0.0, 1.0};

}  // namespace

MoveItWorldResetter::MoveItWorldResetter(std::shared_ptr<IPandaMoveItSceneAdapter> adapter,
                                         double timeout_seconds, double poll_interval_seconds) :
    adapter_(std::move(adapter)), timeout_seconds_(timeout_seconds),
    poll_interval_seconds_(poll_interval_seconds)
{
}

ActionResult MoveItWorldResetter::reset(const Pose3d & target_pose)
{
  if (!adapter_) {
    return resetFailure(ActionStatus::FAILED, "MOVEIT_RESET_ADAPTER_MISSING",
                        "MoveIt world reset requires a scene adapter");
  }
  if (!std::isfinite(timeout_seconds_) || !std::isfinite(poll_interval_seconds_) ||
      timeout_seconds_ <= 0.0 || poll_interval_seconds_ <= 0.0) {
    return resetFailure(ActionStatus::FAILED, "MOVEIT_RESET_TIMING_INVALID",
                        "MoveIt world reset timeout and poll interval must be finite and positive");
  }
  if (!validPose(target_pose)) {
    return resetFailure(
      ActionStatus::FAILED, "MOVEIT_RESET_TARGET_INVALID",
      "MoveIt world reset target must contain a finite position and valid quaternion");
  }

  auto table_upsert = adapter_->upsertTableWorldPose(kCanonicalTablePose);
  if (table_upsert.status != ActionStatus::SUCCEEDED) {
    return table_upsert;
  }

  const auto initial = adapter_->observe();
  if (!initial) {
    return resetFailure(ActionStatus::FAILED, "MOVEIT_RESET_OBSERVATION_FAILED",
                        "MoveIt Planning Scene could not be observed before reset");
  }
  if (initial->task_object_attached) {
    auto detach = adapter_->detachTaskObject();
    if (detach.status != ActionStatus::SUCCEEDED) {
      return detach;
    }
    const auto detach_deadline =
      std::chrono::steady_clock::now() + std::chrono::duration<double>(timeout_seconds_);
    bool detached = false;
    while (std::chrono::steady_clock::now() < detach_deadline) {
      const auto state = adapter_->observe();
      if (state && !state->task_object_attached) {
        detached = true;
        break;
      }
      std::this_thread::sleep_for(std::chrono::duration<double>(poll_interval_seconds_));
    }
    if (!detached) {
      return resetFailure(ActionStatus::TIMED_OUT, "MOVEIT_RESET_DETACH_TIMEOUT",
                          "MoveIt Coke did not converge to detached state");
    }
  }

  auto upsert = adapter_->upsertTaskObjectWorldPose(target_pose);
  if (upsert.status != ActionStatus::SUCCEEDED) {
    return upsert;
  }

  const auto sync_deadline =
    std::chrono::steady_clock::now() + std::chrono::duration<double>(timeout_seconds_);
  while (std::chrono::steady_clock::now() < sync_deadline) {
    const auto state = adapter_->observe();
    if (state && state->table_in_world && state->table_world_pose &&
        poseMatches(*state->table_world_pose, kCanonicalTablePose) &&
        !state->task_object_attached && state->task_object_in_world &&
        state->task_object_world_pose && poseMatches(*state->task_object_world_pose, target_pose)) {
      return {ActionStatus::SUCCEEDED, std::nullopt};
    }
    std::this_thread::sleep_for(std::chrono::duration<double>(poll_interval_seconds_));
  }
  return resetFailure(ActionStatus::TIMED_OUT, "MOVEIT_RESET_SYNC_TIMEOUT",
                      "MoveIt table and Coke did not converge to canonical world poses");
}

}  // namespace panda_gazebo_demo::pick_place
