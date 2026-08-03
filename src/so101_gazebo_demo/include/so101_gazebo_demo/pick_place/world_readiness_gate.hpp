#pragma once

#include <chrono>
#include <cstddef>
#include <optional>
#include <string>

#include "so101_gazebo_demo/pick_place/domain_types.hpp"

namespace so101_gazebo_demo::pick_place
{

class IWorldObserver;

class WorldReadinessGate
{
public:
  WorldReadinessGate(IWorldObserver & observer,
                     std::chrono::milliseconds poll_interval = std::chrono::milliseconds(50),
                     std::size_t required_consecutive_ready_observations = 20);

  [[nodiscard]] std::optional<Failure> waitForReady(const std::string & expected_session_id,
                                                    std::chrono::milliseconds timeout);

private:
  IWorldObserver & observer_;
  std::chrono::milliseconds poll_interval_;
  std::size_t required_consecutive_ready_observations_;
};

}  // namespace so101_gazebo_demo::pick_place
