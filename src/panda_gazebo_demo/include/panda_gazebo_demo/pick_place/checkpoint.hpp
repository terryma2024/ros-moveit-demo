#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include "panda_gazebo_demo/pick_place/domain_types.hpp"
#include "panda_gazebo_demo/pick_place/world_observer.hpp"

namespace panda_gazebo_demo::pick_place
{

struct ExpectedWorldState
{
  Pose3d tcp_pose_world{};
  bool coke_attached{false};
  std::vector<std::string> required_world_objects;
};

struct Checkpoint
{
  std::uint32_t schema_version{1};
  std::string run_id;
  std::uint64_t sequence{0};
  RunMode source_mode{RunMode::EXECUTE};
  State last_completed_state{State::IDLE};
  State next_state{State::IDLE};
  ExpectedWorldState expected;
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
