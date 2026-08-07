#pragma once
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <vector>
#include "pick_place_common/domain_types.hpp"
#include "pick_place_common/world_observer.hpp"
namespace pick_place_common
{
enum class CheckpointPhase
{
  FORWARD,
  RECOVERY
};
struct ExpectedWorldState
{
  Pose3d tcp_pose_world{};
  bool gripper_open{false};
  std::map<std::string, double> joint_positions;
  std::map<std::string, Pose3d> moveit_world_object_poses;
  std::optional<bool> moveit_task_object_attached;
  std::optional<Pose3d> gazebo_task_object_pose_world;
  std::optional<bool> gazebo_task_object_attached;
  std::optional<bool> gazebo_task_object_stationary;
  std::optional<std::uint64_t> gazebo_pose_sequence;
  std::optional<std::int64_t> observation_timestamp_ns;
  std::optional<std::int64_t> gazebo_pose_timestamp_ns;
  std::optional<bool> gazebo_task_object_intended_support_contact;
  std::vector<std::string> gazebo_task_object_support_collision_names;
  std::optional<std::int64_t> gazebo_support_contact_timestamp_ns;
  std::vector<std::string> required_world_objects;
};
struct Checkpoint
{
  std::uint32_t schema_version{4};
  std::string run_id;
  std::uint64_t sequence{0};
  RunMode source_mode{RunMode::EXECUTE};
  CheckpointPhase phase{CheckpointPhase::FORWARD};
  State last_completed_state{State::IDLE};
  std::optional<State> failed_state;
  std::optional<Failure> original_failure;
  State next_state{State::IDLE};
  ExpectedWorldState expected;
  std::string configuration_fingerprint;
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
}  // namespace pick_place_common
