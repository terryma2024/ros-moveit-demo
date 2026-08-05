#pragma once
#include <cstdint>
#include <optional>
#include <string>
#include "pick_place_common/domain_types.hpp"
namespace pick_place_common
{
struct SimulationSessionIdResolution { std::optional<std::string> value; std::string error; };
SimulationSessionIdResolution resolveSimulationSessionId(RunMode, bool resume,
  std::string configured_id, std::uint64_t unix_timestamp_milliseconds);
}  // namespace pick_place_common
