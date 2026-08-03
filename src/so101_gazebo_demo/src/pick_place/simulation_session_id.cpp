#include "so101_gazebo_demo/pick_place/simulation_session_id.hpp"
namespace so101_gazebo_demo::pick_place
{
SimulationSessionIdResolution resolveSimulationSessionId(RunMode mode, bool resume,
                                                         std::string configured_id,
                                                         std::uint64_t unix_timestamp_milliseconds)
{
  if (resume && configured_id.empty())
    return {std::nullopt,
            "simulation_session_id is required for resume to reject stale checkpoints"};
  if (resume || mode == RunMode::EXECUTE)
    return {configured_id.empty()
              ? std::optional<std::string>{"execute-" + std::to_string(unix_timestamp_milliseconds)}
              : std::optional<std::string>{std::move(configured_id)},
            ""};
  return {};
}
}  // namespace so101_gazebo_demo::pick_place
