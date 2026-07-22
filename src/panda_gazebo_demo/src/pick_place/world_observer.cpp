#include "panda_gazebo_demo/pick_place/world_observer.hpp"

#include <cmath>
#include <limits>

namespace panda_gazebo_demo::pick_place
{

double positionDistance(const Pose3d & lhs, const Pose3d & rhs) noexcept
{
  const auto dx = lhs.x - rhs.x;
  const auto dy = lhs.y - rhs.y;
  const auto dz = lhs.z - rhs.z;
  return std::sqrt(dx * dx + dy * dy + dz * dz);
}

double orientationDistance(const Pose3d & lhs, const Pose3d & rhs) noexcept
{
  const auto lhs_norm = std::sqrt(
    lhs.qx * lhs.qx + lhs.qy * lhs.qy + lhs.qz * lhs.qz + lhs.qw * lhs.qw);
  const auto rhs_norm = std::sqrt(
    rhs.qx * rhs.qx + rhs.qy * rhs.qy + rhs.qz * rhs.qz + rhs.qw * rhs.qw);
  if (lhs_norm <= std::numeric_limits<double>::epsilon() ||
    rhs_norm <= std::numeric_limits<double>::epsilon())
  {
    return std::numeric_limits<double>::infinity();
  }
  const auto dot = (lhs.qx * rhs.qx + lhs.qy * rhs.qy + lhs.qz * rhs.qz + lhs.qw * rhs.qw) /
    (lhs_norm * rhs_norm);
  return 2.0 * std::acos(std::min(1.0, std::abs(dot)));
}

}  // namespace panda_gazebo_demo::pick_place
