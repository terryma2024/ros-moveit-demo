#pragma once
#include <cstdint>
#include <optional>
#include <string>
#include "so101_gazebo_demo/pick_place/domain_types.hpp"
namespace so101_gazebo_demo::pick_place
{
struct SimulationSessionIdResolution { std::optional<std::string> value; std::string error; };
SimulationSessionIdResolution resolveSimulationSessionId(RunMode mode, bool resume,
  std::string configured_id, std::uint64_t unix_timestamp_milliseconds);
}  // namespace so101_gazebo_demo::pick_place
