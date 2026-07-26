#pragma once
#include <cstdint>
#include <optional>
#include <string>
#include "so101_gazebo_demo/pick_place/domain_types.hpp"
namespace so101_gazebo_demo::pick_place
{
enum class CheckpointPhase { FORWARD, RECOVERY };
struct Checkpoint { std::uint32_t schema_version{3}; std::string run_id; std::uint64_t sequence{0};
  RunMode source_mode{RunMode::EXECUTE}; CheckpointPhase phase{CheckpointPhase::FORWARD};
  State last_completed_state{State::IDLE}; std::optional<State> failed_state;
  std::optional<Failure> original_failure; State next_state{State::IDLE};
  std::string configuration_hash; std::string simulation_session_id; bool resumable{true}; };
struct CheckpointLoadResult { std::optional<Checkpoint> checkpoint; std::optional<Failure> failure; };
class ICheckpointStore { public: virtual ~ICheckpointStore() = default;
  [[nodiscard]] virtual std::optional<Failure> commit(const Checkpoint &) = 0;
  [[nodiscard]] virtual CheckpointLoadResult loadLatestCompatible() = 0; };
}  // namespace so101_gazebo_demo::pick_place
