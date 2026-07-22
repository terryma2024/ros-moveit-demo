#include "panda_gazebo_demo/pick_place/world_observer.hpp"

#include <cmath>

namespace panda_gazebo_demo::pick_place
{

double positionDistance(const Pose3d & lhs, const Pose3d & rhs) noexcept
{
  const auto dx = lhs.x - rhs.x;
  const auto dy = lhs.y - rhs.y;
  const auto dz = lhs.z - rhs.z;
  return std::sqrt(dx * dx + dy * dy + dz * dz);
}

}  // namespace panda_gazebo_demo::pick_place
