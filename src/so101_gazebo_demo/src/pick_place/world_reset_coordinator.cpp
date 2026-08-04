#include "so101_gazebo_demo/pick_place/world_reset_coordinator.hpp"

#include "so101_gazebo_demo/pick_place/fingertip_pad_gap_calibration_data.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <map>
#include <string>
#include <thread>
#include <utility>

namespace so101_gazebo_demo::pick_place
{
namespace
{

ActionResult resetFailure(ActionStatus status, std::string code, std::string message,
                          std::map<std::string, double> metrics = {})
{
  return {status, Failure{FailureCategory::WORLD_INCONSISTENCY, std::move(code), std::move(message),
                          std::move(metrics)}};
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

bool completeJointEvidence(const CurrentJointStateEvidence & evidence,
                           const WorldResetConfig & config)
{
  if (evidence.joint_names != config.arm_joints ||
      evidence.positions.size() != config.arm_home_positions.size() ||
      evidence.velocities.size() != config.arm_home_positions.size() ||
      !evidence.gripper_position || !evidence.gripper_velocity ||
      evidence.received_at == std::chrono::steady_clock::time_point{}) {
    return false;
  }
  return std::all_of(evidence.positions.begin(), evidence.positions.end(),
                     [](double value) { return std::isfinite(value); }) &&
         std::all_of(evidence.velocities.begin(), evidence.velocities.end(),
                     [](double value) { return std::isfinite(value); }) &&
         std::isfinite(*evidence.gripper_position) && std::isfinite(*evidence.gripper_velocity);
}

bool gripperMatches(const CurrentJointStateEvidence & evidence, double target,
                    const WorldResetConfig & config)
{
  return completeJointEvidence(evidence, config) &&
         std::abs(*evidence.gripper_position - target) <= config.gripper_position_tolerance &&
         std::abs(*evidence.gripper_velocity) <= config.joint_velocity_tolerance;
}

bool gripperHomeMatches(const CurrentJointStateEvidence & evidence, const WorldResetConfig & config)
{
  namespace pad_calibration = fingertip_pad_calibration;
  return gripperMatches(evidence, config.q6_home_position, config) &&
         *evidence.gripper_position >=
           config.q6_safe_lower - pad_calibration::kControllerEndpointEpsilonRad;
}

bool armMatches(const CurrentJointStateEvidence & evidence, const WorldResetConfig & config)
{
  if (!completeJointEvidence(evidence, config))
    return false;
  for (std::size_t i = 0; i < config.arm_home_positions.size(); ++i) {
    if (std::abs(evidence.positions[i] - config.arm_home_positions[i]) >
          config.arm_joint_position_tolerance ||
        std::abs(evidence.velocities[i]) > config.joint_velocity_tolerance) {
      return false;
    }
  }
  return true;
}

std::map<std::string, double>
gripperMetrics(const std::optional<CurrentJointStateEvidence> & evidence, double target)
{
  std::map<std::string, double> metrics{{"expected_q6", target}};
  if (evidence && evidence->gripper_position) {
    metrics["actual_q6"] = *evidence->gripper_position;
  }
  if (evidence && evidence->gripper_velocity) {
    metrics["actual_q6_velocity"] = *evidence->gripper_velocity;
  }
  return metrics;
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

bool setPoseSucceededOrDurablyConvergedAfterTimeout(
  const ActionResult & command, const std::shared_ptr<IGazeboResetAdapter> & gazebo,
  const Pose3d & expected_pose, std::uint64_t pose_revision_before, const WorldResetConfig & config)
{
  if (command.status == ActionStatus::SUCCEEDED) {
    return true;
  }
  if (command.status != ActionStatus::TIMED_OUT || !command.failure ||
      command.failure->code != "GAZEBO_SET_POSE_TIMEOUT") {
    return false;
  }
  return pollUntil(config.timeout_seconds, config.poll_interval_seconds,
                   [&gazebo, &expected_pose, pose_revision_before, &config]() {
                     const auto state = gazebo->observe();
                     return state && state->pose_revision > pose_revision_before &&
                            poseMatches(state->task_object_world_pose, expected_pose, config);
                   });
}

}  // namespace

WorldResetCoordinator::WorldResetCoordinator(std::shared_ptr<IGazeboResetAdapter> gazebo,
                                             std::shared_ptr<IMoveItSceneAdapter> moveit,
                                             std::shared_ptr<IRobotHomeResetAdapter> robot,
                                             WorldResetConfig config) :
    gazebo_(std::move(gazebo)), moveit_(std::move(moveit)), robot_(std::move(robot)),
    config_(std::move(config))
{
}

ActionResult WorldResetCoordinator::reset()
{
  if (!gazebo_ || !moveit_ || !robot_) {
    return resetFailure(ActionStatus::FAILED, "WORLD_RESET_ADAPTER_MISSING",
                        "Gazebo, MoveIt, and robot home reset adapters are required");
  }
  if (!std::isfinite(config_.timeout_seconds) || !std::isfinite(config_.poll_interval_seconds) ||
      config_.timeout_seconds <= 0.0 || config_.poll_interval_seconds <= 0.0 ||
      config_.position_tolerance < 0.0 || config_.orientation_tolerance_rad < 0.0 ||
      config_.arm_joints.empty() ||
      config_.arm_joints.size() != config_.arm_home_positions.size() ||
      !std::all_of(config_.arm_home_positions.begin(), config_.arm_home_positions.end(),
                   [](double value) { return std::isfinite(value); }) ||
      !std::isfinite(config_.q6_release_position) || !std::isfinite(config_.q6_safe_lower) ||
      !std::isfinite(config_.q6_home_position) ||
      !std::isfinite(config_.arm_joint_position_tolerance) ||
      !std::isfinite(config_.gripper_position_tolerance) ||
      !std::isfinite(config_.joint_velocity_tolerance) ||
      config_.arm_joint_position_tolerance < 0.0 || config_.gripper_position_tolerance < 0.0 ||
      config_.joint_velocity_tolerance < 0.0 || !validPose(config_.table_pose) ||
      !validPose(config_.pedestal_pose) || !validPose(config_.task_object_pose) ||
      !validPose(config_.reset_parking_task_object_pose)) {
    return resetFailure(ActionStatus::FAILED, "WORLD_RESET_CONFIG_INVALID",
                        "Reset timing, tolerances, and canonical poses must be valid");
  }
  if (config_.q6_home_position < config_.q6_safe_lower) {
    return resetFailure(
      ActionStatus::FAILED, "Q6_BELOW_SAFE_LOWER_LIMIT",
      "Reset q6 home target must not cross the fingertip-pad safety floor",
      {{"requested_q6", config_.q6_home_position}, {"required_q6", config_.q6_safe_lower}});
  }

  auto gazebo_state = gazebo_->observe();
  auto moveit_state = moveit_->observe();
  if (!gazebo_state || !moveit_state) {
    return resetFailure(ActionStatus::FAILED, "WORLD_RESET_INITIAL_OBSERVATION_FAILED",
                        "Both Gazebo and MoveIt current facts are required before reset");
  }
  const auto initial_joints = robot_->observeJoints();
  if (!initial_joints || !completeJointEvidence(*initial_joints, config_)) {
    return resetFailure(ActionStatus::FAILED, "WORLD_RESET_INITIAL_JOINT_OBSERVATION_FAILED",
                        "Complete finite arm and gripper joint evidence is required before reset");
  }

  auto command = robot_->cancelArmAndWait();
  if (command.status != ActionStatus::SUCCEEDED)
    return command;

  if (gazebo_state->task_object_attached) {
    auto command = gazebo_->detachTaskObject();
    if (command.status != ActionStatus::SUCCEEDED) {
      return command;
    }
    if (!pollUntil(config_.timeout_seconds, config_.poll_interval_seconds, [this]() {
          const auto state = gazebo_->observe();
          return state && !state->task_object_attached;
        })) {
      return resetFailure(ActionStatus::TIMED_OUT, "WORLD_RESET_GAZEBO_DETACH_TIMEOUT",
                          "Gazebo TaskObject did not converge to detached");
    }
  }

  if (moveit_state->task_object_attached) {
    auto command = moveit_->detachTaskObject();
    if (command.status != ActionStatus::SUCCEEDED) {
      return command;
    }
    if (!pollUntil(config_.timeout_seconds, config_.poll_interval_seconds, [this]() {
          const auto state = moveit_->observe();
          return state && !state->task_object_attached && state->task_object_in_world &&
                 state->attached_link.empty() && state->touch_links.empty();
        })) {
      return resetFailure(ActionStatus::TIMED_OUT, "WORLD_RESET_MOVEIT_DETACH_TIMEOUT",
                          "MoveIt TaskObject did not converge to detached world membership");
    }
  }

  gazebo_state = gazebo_->observe();
  if (!gazebo_state) {
    return resetFailure(ActionStatus::FAILED, "WORLD_RESET_GAZEBO_OBSERVATION_FAILED",
                        "Gazebo facts became unavailable before parking");
  }
  const auto parking_pose_revision_before = gazebo_state->pose_revision;
  command = gazebo_->setTaskObjectWorldPose(config_.reset_parking_task_object_pose);
  if (!setPoseSucceededOrDurablyConvergedAfterTimeout(command, gazebo_,
                                                      config_.reset_parking_task_object_pose,
                                                      parking_pose_revision_before, config_))
    return command;
  command = moveit_->upsertTableWorldPose(config_.table_pose);
  if (command.status != ActionStatus::SUCCEEDED)
    return command;
  command = moveit_->upsertPedestalWorldPose(config_.pedestal_pose);
  if (command.status != ActionStatus::SUCCEEDED)
    return command;
  command = moveit_->upsertTaskObjectWorldPose(config_.reset_parking_task_object_pose);
  if (command.status != ActionStatus::SUCCEEDED)
    return command;

  if (!pollUntil(config_.timeout_seconds, config_.poll_interval_seconds,
                 [this, parking_pose_revision_before]() {
                   const auto gazebo = gazebo_->observe();
                   const auto moveit = moveit_->observe();
                   return gazebo && moveit && !gazebo->task_object_attached &&
                          gazebo->pose_revision > parking_pose_revision_before &&
                          poseMatches(gazebo->task_object_world_pose,
                                      config_.reset_parking_task_object_pose, config_) &&
                          !moveit->task_object_attached && moveit->task_object_in_world &&
                          moveit->attached_link.empty() && moveit->touch_links.empty() &&
                          moveit->task_object_world_pose &&
                          poseMatches(*moveit->task_object_world_pose,
                                      config_.reset_parking_task_object_pose, config_) &&
                          moveit->table_in_world && moveit->table_world_pose &&
                          poseMatches(*moveit->table_world_pose, config_.table_pose, config_) &&
                          moveit->pedestal_in_world && moveit->pedestal_world_pose &&
                          poseMatches(*moveit->pedestal_world_pose, config_.pedestal_pose,
                                      config_) &&
                          poseMatches(gazebo->task_object_world_pose,
                                      *moveit->task_object_world_pose, config_);
                 })) {
    return resetFailure(ActionStatus::TIMED_OUT, "WORLD_RESET_PARKING_CONVERGENCE_TIMEOUT",
                        "Gazebo and MoveIt did not converge to detached parking 6D facts");
  }

  command = robot_->commandGripper(config_.q6_release_position);
  if (command.status != ActionStatus::SUCCEEDED)
    return command;
  std::optional<CurrentJointStateEvidence> latest_joints;
  if (!pollUntil(config_.timeout_seconds, config_.poll_interval_seconds, [this, &latest_joints]() {
        latest_joints = robot_->observeJoints();
        return latest_joints &&
               gripperMatches(*latest_joints, config_.q6_release_position, config_);
      })) {
    return resetFailure(ActionStatus::TIMED_OUT, "WORLD_RESET_GRIPPER_RELEASE_TIMEOUT",
                        "Gripper did not converge to the full-open release state",
                        gripperMetrics(latest_joints, config_.q6_release_position));
  }

  const auto arm_plan = robot_->planArmHome(config_.arm_home_positions);
  if (arm_plan.action.status != ActionStatus::SUCCEEDED)
    return arm_plan.action;
  if (!arm_plan.artifact || arm_plan.artifact->trajectory_points == 0) {
    return resetFailure(ActionStatus::FAILED, "WORLD_RESET_ARM_HOME_PLAN_INVALID",
                        "Arm home planning did not produce a non-empty executable trajectory");
  }
  command = robot_->executeArmHome(*arm_plan.artifact);
  if (command.status != ActionStatus::SUCCEEDED)
    return command;
  if (!pollUntil(config_.timeout_seconds, config_.poll_interval_seconds, [this, &latest_joints]() {
        latest_joints = robot_->observeJoints();
        return latest_joints && armMatches(*latest_joints, config_);
      })) {
    std::map<std::string, double> metrics;
    if (latest_joints) {
      for (std::size_t i = 0; i < config_.arm_home_positions.size(); ++i) {
        metrics["expected_" + config_.arm_joints[i]] = config_.arm_home_positions[i];
        if (i < latest_joints->positions.size()) {
          metrics["actual_" + config_.arm_joints[i]] = latest_joints->positions[i];
        }
        if (i < latest_joints->velocities.size()) {
          metrics["actual_velocity_" + config_.arm_joints[i]] = latest_joints->velocities[i];
        }
      }
    }
    return resetFailure(ActionStatus::TIMED_OUT, "WORLD_RESET_ARM_HOME_TIMEOUT",
                        "Arm joints did not converge to the stationary home state",
                        std::move(metrics));
  }

  gazebo_state = gazebo_->observe();
  if (!gazebo_state) {
    return resetFailure(ActionStatus::FAILED, "WORLD_RESET_GAZEBO_OBSERVATION_FAILED",
                        "Gazebo facts became unavailable before canonical pose reset");
  }
  const auto pose_revision_before = gazebo_state->pose_revision;
  command = gazebo_->setTaskObjectWorldPose(config_.task_object_pose);
  if (!setPoseSucceededOrDurablyConvergedAfterTimeout(command, gazebo_, config_.task_object_pose,
                                                      pose_revision_before, config_)) {
    return command;
  }
  command = moveit_->upsertTaskObjectWorldPose(config_.task_object_pose);
  if (command.status != ActionStatus::SUCCEEDED) {
    return command;
  }

  if (!pollUntil(
        config_.timeout_seconds, config_.poll_interval_seconds, [this, pose_revision_before]() {
          const auto gazebo = gazebo_->observe();
          const auto moveit = moveit_->observe();
          return gazebo && moveit && !gazebo->task_object_attached &&
                 gazebo->pose_revision > pose_revision_before &&
                 poseMatches(gazebo->task_object_world_pose, config_.task_object_pose, config_) &&
                 !moveit->task_object_attached && moveit->task_object_in_world &&
                 moveit->attached_link.empty() && moveit->touch_links.empty() &&
                 moveit->task_object_world_pose &&
                 poseMatches(*moveit->task_object_world_pose, config_.task_object_pose, config_) &&
                 moveit->table_in_world && moveit->table_world_pose &&
                 poseMatches(*moveit->table_world_pose, config_.table_pose, config_) &&
                 moveit->pedestal_in_world && moveit->pedestal_world_pose &&
                 poseMatches(*moveit->pedestal_world_pose, config_.pedestal_pose, config_) &&
                 poseMatches(gazebo->task_object_world_pose, *moveit->task_object_world_pose,
                             config_);
        })) {
    return resetFailure(ActionStatus::TIMED_OUT, "WORLD_RESET_CANONICAL_RESTORE_TIMEOUT",
                        "Gazebo and MoveIt did not converge to detached canonical 6D facts");
  }

  command = robot_->commandGripper(config_.q6_home_position);
  if (command.status != ActionStatus::SUCCEEDED)
    return command;
  if (!pollUntil(config_.timeout_seconds, config_.poll_interval_seconds, [this, &latest_joints]() {
        latest_joints = robot_->observeJoints();
        return latest_joints && armMatches(*latest_joints, config_) &&
               gripperHomeMatches(*latest_joints, config_);
      })) {
    return resetFailure(ActionStatus::TIMED_OUT, "WORLD_RESET_GRIPPER_HOME_TIMEOUT",
                        "Gripper did not converge to the stationary SRDF home state",
                        gripperMetrics(latest_joints, config_.q6_home_position));
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

}  // namespace so101_gazebo_demo::pick_place
