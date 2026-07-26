#pragma once
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <vector>
#include "so101_gazebo_demo/pick_place/domain_types.hpp"
#include "so101_gazebo_demo/pick_place/world_observer.hpp"
namespace so101_gazebo_demo::pick_place
{
enum class CheckpointPhase
{
  FORWARD,
  RECOVERY
};
// Schema v3 intentionally excludes attached-link and touch-link metadata. Those fields remain
// runtime transition evidence; adding them to persisted resume identity requires a new schema.
struct ExpectedWorldState
{
  Pose3d tcp_pose_world{};
  bool gripper_open{false};
  std::map<std::string, double> joint_positions;
  std::map<std::string, Pose3d> moveit_world_object_poses;
  std::optional<bool> moveit_coke_attached;
  std::optional<Pose3d> gazebo_coke_pose_world;
  std::optional<bool> gazebo_coke_attached;
  std::optional<bool> gazebo_coke_stationary;
  std::vector<std::string> required_world_objects;
};
struct Checkpoint
{
  std::uint32_t schema_version{3};
  std::string run_id;
  std::uint64_t sequence{0};
  RunMode source_mode{RunMode::EXECUTE};
  CheckpointPhase phase{CheckpointPhase::FORWARD};
  State last_completed_state{State::IDLE};
  std::optional<State> failed_state;
  std::optional<Failure> original_failure;
  State next_state{State::IDLE};
  ExpectedWorldState expected;
  std::string configuration_hash;
  std::string simulation_session_id;
  bool resumable{true};
};
struct CheckpointLoadResult
{
  std::optional<Checkpoint> checkpoint;
  std::optional<Failure> failure;
};
class ICheckpointStore
{
public:
  virtual ~ICheckpointStore() = default;
  virtual std::optional<Failure> commit(const Checkpoint &) = 0;
  virtual CheckpointLoadResult loadLatestCompatible() = 0;
};
}  // namespace so101_gazebo_demo::pick_place
