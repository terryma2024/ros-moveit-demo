#pragma once

#include "panda_gazebo_demo/pick_place/domain_types.hpp"

#include <cstdint>
#include <optional>
#include <string>

namespace panda_gazebo_demo::pick_place
{

struct SimulationSessionIdResolution
{
  std::optional<std::string> value;
  std::string error;
};

SimulationSessionIdResolution resolveSimulationSessionId(RunMode mode, bool resume,
                                                         std::string configured_id,
                                                         std::uint64_t unix_timestamp_milliseconds);

}  // namespace panda_gazebo_demo::pick_place
