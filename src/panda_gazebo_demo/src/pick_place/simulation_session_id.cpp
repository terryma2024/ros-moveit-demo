#include "panda_gazebo_demo/pick_place/simulation_session_id.hpp"

#include <utility>

namespace panda_gazebo_demo::pick_place
{

SimulationSessionIdResolution resolveSimulationSessionId(
  RunMode mode, bool resume, std::string configured_id,
  std::uint64_t unix_timestamp_milliseconds)
{
  if (resume) {
    if (configured_id.empty()) {
      return {std::nullopt,
        "simulation_session_id is required for resume to reject stale checkpoints"};
    }
    return {std::move(configured_id), ""};
  }
  if (mode != RunMode::EXECUTE) {
    return {std::nullopt, ""};
  }
  if (!configured_id.empty()) {
    return {std::move(configured_id), ""};
  }
  return {"execute-" + std::to_string(unix_timestamp_milliseconds), ""};
}

}  // namespace panda_gazebo_demo::pick_place
