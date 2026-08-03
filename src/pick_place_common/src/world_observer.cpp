#include "pick_place_common/world_observer.hpp"

#include <cmath>
#include <limits>

namespace pick_place_common
{
double positionDistance(const Pose3d & lhs, const Pose3d & rhs) noexcept
{
  if (!std::isfinite(lhs.x) || !std::isfinite(lhs.y) || !std::isfinite(lhs.z) ||
      !std::isfinite(rhs.x) || !std::isfinite(rhs.y) || !std::isfinite(rhs.z)) {
    return std::numeric_limits<double>::infinity();
  }
  const auto dx = lhs.x - rhs.x;
  const auto dy = lhs.y - rhs.y;
  const auto dz = lhs.z - rhs.z;
  const auto distance = std::sqrt(dx * dx + dy * dy + dz * dz);
  return std::isfinite(distance) ? distance : std::numeric_limits<double>::infinity();
}
double orientationDistance(const Pose3d & lhs, const Pose3d & rhs) noexcept
{
  if (!std::isfinite(lhs.qx) || !std::isfinite(lhs.qy) || !std::isfinite(lhs.qz) ||
      !std::isfinite(lhs.qw) || !std::isfinite(rhs.qx) || !std::isfinite(rhs.qy) ||
      !std::isfinite(rhs.qz) || !std::isfinite(rhs.qw)) {
    return std::numeric_limits<double>::infinity();
  }
  const auto lhs_norm =
    std::sqrt(lhs.qx * lhs.qx + lhs.qy * lhs.qy + lhs.qz * lhs.qz + lhs.qw * lhs.qw);
  const auto rhs_norm =
    std::sqrt(rhs.qx * rhs.qx + rhs.qy * rhs.qy + rhs.qz * rhs.qz + rhs.qw * rhs.qw);
  if (!std::isfinite(lhs_norm) || !std::isfinite(rhs_norm) ||
      lhs_norm <= std::numeric_limits<double>::epsilon() ||
      rhs_norm <= std::numeric_limits<double>::epsilon()) {
    return std::numeric_limits<double>::infinity();
  }
  const auto dot =
    (lhs.qx * rhs.qx + lhs.qy * rhs.qy + lhs.qz * rhs.qz + lhs.qw * rhs.qw) /
    (lhs_norm * rhs_norm);
  if (!std::isfinite(dot)) return std::numeric_limits<double>::infinity();
  return 2.0 * std::acos(std::min(1.0, std::abs(dot)));
}
}  // namespace pick_place_common
