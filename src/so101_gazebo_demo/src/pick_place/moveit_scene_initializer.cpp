#include "so101_gazebo_demo/pick_place/moveit_scene_initializer.hpp"

#include <algorithm>
#include <cmath>
#include <thread>

#include "so101_gazebo_demo/pick_place/moveit_scene_adapter.hpp"
#include "so101_gazebo_demo/pick_place/so101_joint_motion_adapter.hpp"

namespace so101_gazebo_demo::pick_place
{

namespace
{

bool allFinite(const std::vector<double> & values)
{
  return std::all_of(values.begin(), values.end(),
                     [](double v) { return std::isfinite(v); });
}

bool evidenceComplete(const std::optional<CurrentJointStateEvidence> & evidence,
                      const std::vector<std::string> & expected_names)
{
  if (!evidence) return false;
  if (evidence->joint_names != expected_names) return false;
  if (evidence->positions.size() != expected_names.size() ||
      evidence->velocities.size() != expected_names.size()) return false;
  if (!allFinite(evidence->positions) || !allFinite(evidence->velocities)) return false;
  if (!evidence->gripper_position || !std::isfinite(*evidence->gripper_position)) return false;
  if (!evidence->gripper_velocity || !std::isfinite(*evidence->gripper_velocity)) return false;
  return true;
}

double positionDistance(const Pose3d & a, const Pose3d & b)
{
  const auto dx = a.x - b.x;
  const auto dy = a.y - b.y;
  const auto dz = a.z - b.z;
  return std::sqrt(dx * dx + dy * dy + dz * dz);
}

double quaternionAngularDistance(const Pose3d & a, const Pose3d & b)
{
  const auto dot = std::clamp(
    std::abs(a.qx * b.qx + a.qy * b.qy + a.qz * b.qz + a.qw * b.qw), 0.0, 1.0);
  return 2.0 * std::acos(dot);
}

bool poseMatches(const Pose3d & actual, const Pose3d & expected,
                 double position_tolerance, double angular_tolerance)
{
  if (!std::isfinite(actual.x) || !std::isfinite(actual.y) || !std::isfinite(actual.z) ||
      !std::isfinite(actual.qx) || !std::isfinite(actual.qy) ||
      !std::isfinite(actual.qz) || !std::isfinite(actual.qw)) {
    return false;
  }
  return positionDistance(actual, expected) <= position_tolerance &&
         quaternionAngularDistance(actual, expected) <= angular_tolerance;
}

bool sceneConverged(const std::optional<MoveItSceneState> & state,
                    const SO101Profile & profile)
{
  if (!state) return false;
  if (!state->table_in_world || !state->table_world_pose) return false;
  if (!state->pedestal_in_world || !state->pedestal_world_pose) return false;
  if (!state->task_object_in_world || !state->task_object_world_pose) return false;
  if (state->task_object_attached) return false;
  if (!poseMatches(*state->table_world_pose, profile.table_pose, 1e-3, 1e-2)) return false;
  if (!poseMatches(*state->pedestal_world_pose, profile.pedestal_pose, 1e-3, 1e-2)) return false;
  if (!poseMatches(*state->task_object_world_pose, profile.task_object_pose, 1e-3, 1e-2)) return false;
  return true;
}

}  // namespace

MoveItSceneInitializer::MoveItSceneInitializer(
  IJointPlanningBoundary & boundary, IMoveItSceneAdapter & scene,
  std::chrono::milliseconds poll_interval)
: boundary_(boundary), scene_(scene), poll_interval_(poll_interval)
{
}

std::optional<Failure>
MoveItSceneInitializer::initialize(const SO101Profile & profile,
                                   std::chrono::milliseconds timeout)
{
  const auto & expected_names = profile.arm_joints;
  const auto deadline = std::chrono::steady_clock::now() + timeout;

  while (std::chrono::steady_clock::now() < deadline) {
    if (evidenceComplete(boundary_.currentState(), expected_names)) break;
    std::this_thread::sleep_for(poll_interval_);
  }
  if (!evidenceComplete(boundary_.currentState(), expected_names)) {
    return Failure{FailureCategory::OBSERVATION, "JOINT_EVIDENCE_INCOMPLETE",
                   "Timed out waiting for complete joint 1-6 evidence", {}};
  }

  if (const auto r = scene_.upsertTableWorldPose(profile.table_pose);
      r.status != ActionStatus::SUCCEEDED) {
    return r.failure.value_or(Failure{FailureCategory::MOVEIT_SCENE,
      "MOVEIT_TABLE_UPSERT_APPLY_FAILED",
      "Failed to upsert canonical table collision object", {}});
  }
  if (const auto r = scene_.upsertPedestalWorldPose(profile.pedestal_pose);
      r.status != ActionStatus::SUCCEEDED) {
    return r.failure.value_or(Failure{FailureCategory::MOVEIT_SCENE,
      "MOVEIT_PEDESTAL_UPSERT_APPLY_FAILED",
      "Failed to upsert canonical pedestal collision object", {}});
  }
  if (const auto r = scene_.upsertTaskObjectWorldPose(profile.task_object_pose);
      r.status != ActionStatus::SUCCEEDED) {
    return r.failure.value_or(Failure{FailureCategory::MOVEIT_SCENE,
      "MOVEIT_TASK_OBJECT_UPSERT_APPLY_FAILED",
      "Failed to upsert configured task object collision object", {}});
  }

  while (std::chrono::steady_clock::now() < deadline) {
    if (sceneConverged(scene_.observe(), profile)) return std::nullopt;
    std::this_thread::sleep_for(poll_interval_);
  }
  if (sceneConverged(scene_.observe(), profile)) return std::nullopt;

  return Failure{FailureCategory::MOVEIT_SCENE, "MOVEIT_SCENE_EVIDENCE_INCOMPLETE",
                 "Canonical table, pedestal, and task object did not converge in planning scene",
                 {}};
}

}  // namespace so101_gazebo_demo::pick_place
