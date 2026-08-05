#include "so101_gazebo_demo/pick_place/world_readiness_gate.hpp"

#include <cmath>
#include <string>
#include <thread>

#include "so101_gazebo_demo/pick_place/world_observer.hpp"

namespace so101_gazebo_demo::pick_place
{

namespace
{

bool isTransientObservation(const std::string & code)
{
  return code == "ROBOT_STATE_CHANGED_DURING_MOVEIT_OBSERVATION" ||
         code == "GAZEBO_TASK_OBJECT_POSE_UNAVAILABLE" ||
         code == "GAZEBO_ATTACHMENT_STATE_UNAVAILABLE";
}

// Readiness only requires transport fields to be finite; quaternion usability is checked later.
bool finitePoseComponents(const Pose3d & pose)
{
  return std::isfinite(pose.x) && std::isfinite(pose.y) && std::isfinite(pose.z) &&
         std::isfinite(pose.qx) && std::isfinite(pose.qy) && std::isfinite(pose.qz) &&
         std::isfinite(pose.qw);
}

bool snapshotReady(const WorldSnapshot & snapshot, const std::string & expected_session_id)
{
  if (!snapshot.fresh)
    return false;
  if (!snapshot.arm_stationary)
    return false;
  if (!snapshot.gazebo_task_object_pose_world ||
      !finitePoseComponents(*snapshot.gazebo_task_object_pose_world)) {
    return false;
  }
  if (!snapshot.gazebo_task_object_attached)
    return false;
  if (snapshot.simulation_session_id != expected_session_id)
    return false;
  return true;
}

}  // namespace

WorldReadinessGate::WorldReadinessGate(IWorldObserver & observer,
                                       std::chrono::milliseconds poll_interval,
                                       std::size_t required_consecutive_ready_observations) :
    observer_(observer), poll_interval_(poll_interval),
    required_consecutive_ready_observations_(required_consecutive_ready_observations)
{
}

std::optional<Failure> WorldReadinessGate::waitForReady(const std::string & expected_session_id,
                                                        std::chrono::milliseconds timeout)
{
  const auto deadline = std::chrono::steady_clock::now() + timeout;
  std::size_t consecutive_ready_observations = 0;

  while (std::chrono::steady_clock::now() < deadline) {
    const auto result = observer_.observe();
    if (result.snapshot && snapshotReady(*result.snapshot, expected_session_id)) {
      ++consecutive_ready_observations;
      if (consecutive_ready_observations >= required_consecutive_ready_observations_) {
        return std::nullopt;
      }
    } else {
      consecutive_ready_observations = 0;
    }
    if (result.failure && !isTransientObservation(result.failure->code)) {
      return result.failure;
    }
    std::this_thread::sleep_for(poll_interval_);
  }

  return Failure{FailureCategory::OBSERVATION,
                 "WORLD_READINESS_TIMEOUT",
                 "World observation did not become ready within timeout",
                 {}};
}

}  // namespace so101_gazebo_demo::pick_place
