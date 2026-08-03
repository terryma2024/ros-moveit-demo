#include "pick_place_common/world_observer.hpp"

#include <algorithm>
#include <cmath>

namespace pick_place_common
{
double positionDistance(const Pose3d & lhs, const Pose3d & rhs) noexcept
{
  return std::hypot(std::hypot(lhs.x - rhs.x, lhs.y - rhs.y), lhs.z - rhs.z);
}
double orientationDistance(const Pose3d & lhs, const Pose3d & rhs) noexcept
{
  const double dot = std::abs(lhs.qx * rhs.qx + lhs.qy * rhs.qy + lhs.qz * rhs.qz +
                              lhs.qw * rhs.qw);
  return 2.0 * std::acos(std::clamp(dot, 0.0, 1.0));
}
}  // namespace pick_place_common
