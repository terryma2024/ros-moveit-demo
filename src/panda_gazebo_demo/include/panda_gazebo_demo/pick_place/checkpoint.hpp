#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <map>
#include <vector>

#include "panda_gazebo_demo/pick_place/domain_types.hpp"
#include "panda_gazebo_demo/pick_place/world_observer.hpp"

namespace panda_gazebo_demo::pick_place
{

enum class CheckpointPhase
{
  FORWARD,
  RECOVERY,
};

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
  [[nodiscard]] virtual std::optional<Failure> commit(const Checkpoint & checkpoint) = 0;
  [[nodiscard]] virtual CheckpointLoadResult loadLatestCompatible() = 0;
};

}  // namespace panda_gazebo_demo::pick_place
