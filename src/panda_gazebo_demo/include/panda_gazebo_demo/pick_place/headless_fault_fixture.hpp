#pragma once

#include <cmath>
#include <optional>
#include <string>
#include <vector>

#include "panda_gazebo_demo/pick_place/world_observer.hpp"

namespace panda_gazebo_demo::pick_place
{

struct FaultFixtureWaypoints
{
  std::vector<Pose3d> waypoints;
  std::optional<std::string> failure;
};

inline FaultFixtureWaypoints
buildLiftThenLateralWaypoints(const Pose3d & start, double lift_distance, double lateral_offset_y)
{
  const bool finite_start = std::isfinite(start.x) && std::isfinite(start.y) &&
                            std::isfinite(start.z) && std::isfinite(start.qx) &&
                            std::isfinite(start.qy) && std::isfinite(start.qz) &&
                            std::isfinite(start.qw);
  if (!finite_start || !std::isfinite(lift_distance) || !std::isfinite(lateral_offset_y)) {
    return {{}, "fault-fixture pose and offsets must be finite"};
  }
  if (lift_distance <= 1.0e-6 || lift_distance > 0.10) {
    return {{}, "lift_distance must be in (1e-6, 0.10]"};
  }
  if (std::abs(lateral_offset_y) > 0.10) {
    return {{}, "absolute lateral_offset_y must not exceed 0.10"};
  }

  Pose3d lifted = start;
  lifted.z += lift_distance;
  FaultFixtureWaypoints result{{lifted}, std::nullopt};
  if (std::abs(lateral_offset_y) > 1.0e-9) {
    Pose3d lateral = lifted;
    lateral.y += lateral_offset_y;
    result.waypoints.push_back(lateral);
  }
  return result;
}

}  // namespace panda_gazebo_demo::pick_place
