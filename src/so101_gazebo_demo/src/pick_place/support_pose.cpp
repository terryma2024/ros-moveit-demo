#include "so101_gazebo_demo/pick_place/support_pose.hpp"

#include <algorithm>
#include <cmath>

namespace so101_gazebo_demo::pick_place
{
namespace
{

double uprightTilt(const Pose3d & pose) noexcept
{
  if (!isFinitePose(pose))
    return INFINITY;
  const double norm = std::hypot(std::hypot(pose.qx, pose.qy), std::hypot(pose.qz, pose.qw));
  const double local_z_world_z =
    1.0 - 2.0 * (pose.qx * pose.qx + pose.qy * pose.qy) / (norm * norm);
  return std::acos(std::clamp(local_z_world_z, -1.0, 1.0));
}

}  // namespace

bool supportedAtPick(const Pose3d & pose, const SO101Profile & profile) noexcept
{
  const double tilt = uprightTilt(pose);
  return positionDistance(pose, profile.task_object_pose) <=
           profile.task_object_position_drift_tolerance &&
         std::isfinite(tilt) && tilt <= profile.place_support_tilt_tolerance_rad;
}

bool supportedAtPlace(const Pose3d & pose, const SO101Profile & profile) noexcept
{
  if (!isFinitePose(pose))
    return false;
  const auto & expected = profile.place_task_object_pose;
  const double xy_error = std::hypot(pose.x - expected.x, pose.y - expected.y);
  const double height_error = std::abs(pose.z - expected.z);
  const double tilt = uprightTilt(pose);
  return std::isfinite(xy_error) && std::isfinite(height_error) && std::isfinite(tilt) &&
         xy_error <= profile.place_support_xy_tolerance &&
         height_error <= profile.place_support_height_tolerance &&
         tilt <= profile.place_support_tilt_tolerance_rad;
}

}  // namespace so101_gazebo_demo::pick_place
