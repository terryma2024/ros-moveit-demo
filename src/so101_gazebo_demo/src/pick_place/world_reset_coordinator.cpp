#include "so101_gazebo_demo/pick_place/world_reset_coordinator.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <string>
#include <thread>
#include <utility>

namespace so101_gazebo_demo::pick_place
{
namespace
{

ActionResult resetFailure(ActionStatus status, std::string code, std::string message)
{
  return {status,
          Failure{FailureCategory::WORLD_INCONSISTENCY, std::move(code), std::move(message), {}}};
}

bool validPose(const Pose3d & pose)
{
  const double values[]{pose.x, pose.y, pose.z, pose.qx, pose.qy, pose.qz, pose.qw};
  return std::all_of(std::begin(values), std::end(values),
                     [](double value) { return std::isfinite(value); }) &&
         std::hypot(std::hypot(pose.qx, pose.qy), std::hypot(pose.qz, pose.qw)) > 1e-12;
}

double positionDistance(const Pose3d & a, const Pose3d & b)
{
  return std::hypot(std::hypot(a.x - b.x, a.y - b.y), a.z - b.z);
}

double orientationDistance(const Pose3d & a, const Pose3d & b)
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

bool poseMatches(const Pose3d & actual, const Pose3d & expected, const WorldResetConfig & config)
{
  return positionDistance(actual, expected) <= config.position_tolerance &&
         orientationDistance(actual, expected) <= config.orientation_tolerance_rad;
}

template <typename Predicate>
bool pollUntil(double timeout_seconds, double poll_interval_seconds, Predicate predicate)
{
  const auto deadline =
    std::chrono::steady_clock::now() + std::chrono::duration<double>(timeout_seconds);
  while (std::chrono::steady_clock::now() < deadline) {
    if (predicate()) {
      return true;
    }
    std::this_thread::sleep_for(std::chrono::duration<double>(poll_interval_seconds));
  }
  return false;
}

}  // namespace

WorldResetCoordinator::WorldResetCoordinator(std::shared_ptr<IGazeboResetAdapter> gazebo,
                                             std::shared_ptr<IMoveItSceneAdapter> moveit,
                                             WorldResetConfig config) :
    gazebo_(std::move(gazebo)), moveit_(std::move(moveit)), config_(config)
{
}

ActionResult WorldResetCoordinator::reset()
{
  if (!gazebo_ || !moveit_) {
    return resetFailure(ActionStatus::FAILED, "WORLD_RESET_ADAPTER_MISSING",
                        "Gazebo and MoveIt reset adapters are required");
  }
  if (!std::isfinite(config_.timeout_seconds) || !std::isfinite(config_.poll_interval_seconds) ||
      config_.timeout_seconds <= 0.0 || config_.poll_interval_seconds <= 0.0 ||
      config_.position_tolerance < 0.0 || config_.orientation_tolerance_rad < 0.0 ||
      !validPose(config_.table_pose) || !validPose(config_.coke_pose)) {
    return resetFailure(ActionStatus::FAILED, "WORLD_RESET_CONFIG_INVALID",
                        "Reset timing, tolerances, and canonical poses must be valid");
  }

  auto gazebo_state = gazebo_->observe();
  auto moveit_state = moveit_->observe();
  if (!gazebo_state || !moveit_state) {
    return resetFailure(ActionStatus::FAILED, "WORLD_RESET_INITIAL_OBSERVATION_FAILED",
                        "Both Gazebo and MoveIt current facts are required before reset");
  }

  if (gazebo_state->coke_attached) {
    const auto command = gazebo_->detachCoke();
    if (command.status != ActionStatus::SUCCEEDED) {
      return command;
    }
    if (!pollUntil(config_.timeout_seconds, config_.poll_interval_seconds, [this]() {
          const auto state = gazebo_->observe();
          return state && !state->coke_attached;
        })) {
      return resetFailure(ActionStatus::TIMED_OUT, "WORLD_RESET_GAZEBO_DETACH_TIMEOUT",
                          "Gazebo Coke did not converge to detached");
    }
  }

  if (moveit_state->coke_attached) {
    const auto command = moveit_->detachCoke();
    if (command.status != ActionStatus::SUCCEEDED) {
      return command;
    }
    if (!pollUntil(config_.timeout_seconds, config_.poll_interval_seconds, [this]() {
          const auto state = moveit_->observe();
          return state && !state->coke_attached && state->coke_in_world &&
                 state->attached_link.empty() && state->touch_links.empty();
        })) {
      return resetFailure(ActionStatus::TIMED_OUT, "WORLD_RESET_MOVEIT_DETACH_TIMEOUT",
                          "MoveIt Coke did not converge to detached world membership");
    }
  }

  gazebo_state = gazebo_->observe();
  if (!gazebo_state) {
    return resetFailure(ActionStatus::FAILED, "WORLD_RESET_GAZEBO_OBSERVATION_FAILED",
                        "Gazebo facts became unavailable before canonical pose reset");
  }
  const auto pose_revision_before = gazebo_state->pose_revision;
  auto command = gazebo_->setCokeWorldPose(config_.coke_pose);
  if (command.status != ActionStatus::SUCCEEDED) {
    return command;
  }
  command = moveit_->upsertTableWorldPose(config_.table_pose);
  if (command.status != ActionStatus::SUCCEEDED) {
    return command;
  }
  command = moveit_->upsertCokeWorldPose(config_.coke_pose);
  if (command.status != ActionStatus::SUCCEEDED) {
    return command;
  }

  if (pollUntil(
        config_.timeout_seconds, config_.poll_interval_seconds, [this, pose_revision_before]() {
          const auto gazebo = gazebo_->observe();
          const auto moveit = moveit_->observe();
          return gazebo && moveit && !gazebo->coke_attached &&
                 gazebo->pose_revision > pose_revision_before &&
                 poseMatches(gazebo->coke_world_pose, config_.coke_pose, config_) &&
                 !moveit->coke_attached && moveit->coke_in_world && moveit->attached_link.empty() &&
                 moveit->touch_links.empty() && moveit->coke_world_pose &&
                 poseMatches(*moveit->coke_world_pose, config_.coke_pose, config_) &&
                 moveit->table_in_world && moveit->table_world_pose &&
                 poseMatches(*moveit->table_world_pose, config_.table_pose, config_) &&
                 poseMatches(gazebo->coke_world_pose, *moveit->coke_world_pose, config_);
        })) {
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }
  return resetFailure(ActionStatus::TIMED_OUT, "WORLD_RESET_CONVERGENCE_TIMEOUT",
                      "Gazebo and MoveIt did not converge to detached canonical 6D facts");
}

}  // namespace so101_gazebo_demo::pick_place
