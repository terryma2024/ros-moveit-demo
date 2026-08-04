#include "pick_place_common/pose_geometry.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

namespace pick_place_common
{
namespace
{

struct Quaternion
{
  double x;
  double y;
  double z;
  double w;
};

std::optional<Quaternion> normalized(const Pose3d & pose) noexcept
{
  if (!hasUsableQuaternion(pose)) return std::nullopt;
  const double norm = std::hypot(std::hypot(pose.qx, pose.qy), std::hypot(pose.qz, pose.qw));
  if (!std::isfinite(norm) || norm == 0.0) return std::nullopt;
  return Quaternion{pose.qx / norm, pose.qy / norm, pose.qz / norm, pose.qw / norm};
}

Quaternion multiply(const Quaternion & lhs, const Quaternion & rhs) noexcept
{
  return {lhs.w * rhs.x + lhs.x * rhs.w + lhs.y * rhs.z - lhs.z * rhs.y,
          lhs.w * rhs.y - lhs.x * rhs.z + lhs.y * rhs.w + lhs.z * rhs.x,
          lhs.w * rhs.z + lhs.x * rhs.y - lhs.y * rhs.x + lhs.z * rhs.w,
          lhs.w * rhs.w - lhs.x * rhs.x - lhs.y * rhs.y - lhs.z * rhs.z};
}

void rotate(const Quaternion & rotation, double x, double y, double z, double & out_x,
            double & out_y, double & out_z) noexcept
{
  const Quaternion vector{x, y, z, 0.0};
  const Quaternion inverse{-rotation.x, -rotation.y, -rotation.z, rotation.w};
  const Quaternion result = multiply(multiply(rotation, vector), inverse);
  out_x = result.x;
  out_y = result.y;
  out_z = result.z;
}

}  // namespace

bool isFinitePose(const Pose3d & pose) noexcept
{
  return std::isfinite(pose.x) && std::isfinite(pose.y) && std::isfinite(pose.z) &&
         std::isfinite(pose.qx) && std::isfinite(pose.qy) && std::isfinite(pose.qz) &&
         std::isfinite(pose.qw);
}

bool hasUsableQuaternion(const Pose3d & pose, double minimum_squared_norm) noexcept
{
  if (!isFinitePose(pose) || !std::isfinite(minimum_squared_norm) || minimum_squared_norm < 0.0) {
    return false;
  }
  const double squared_norm =
    pose.qx * pose.qx + pose.qy * pose.qy + pose.qz * pose.qz + pose.qw * pose.qw;
  return std::isfinite(squared_norm) && squared_norm > minimum_squared_norm;
}

double positionDistance(const Pose3d & lhs, const Pose3d & rhs) noexcept
{
  if (!isFinitePose(lhs) || !isFinitePose(rhs)) return std::numeric_limits<double>::infinity();
  const double distance = std::hypot(std::hypot(lhs.x - rhs.x, lhs.y - rhs.y), lhs.z - rhs.z);
  return std::isfinite(distance) ? distance : std::numeric_limits<double>::infinity();
}

double orientationDistance(const Pose3d & lhs, const Pose3d & rhs) noexcept
{
  const auto lhs_quaternion = normalized(lhs);
  const auto rhs_quaternion = normalized(rhs);
  if (!lhs_quaternion || !rhs_quaternion) return std::numeric_limits<double>::infinity();
  const double dot = lhs_quaternion->x * rhs_quaternion->x +
                     lhs_quaternion->y * rhs_quaternion->y +
                     lhs_quaternion->z * rhs_quaternion->z +
                     lhs_quaternion->w * rhs_quaternion->w;
  if (!std::isfinite(dot)) return std::numeric_limits<double>::infinity();
  double absolute_dot = std::clamp(std::abs(dot), 0.0, 1.0);
  if (1.0 - absolute_dot <= 4.0 * std::numeric_limits<double>::epsilon()) absolute_dot = 1.0;
  return 2.0 * std::acos(absolute_dot);
}

std::optional<Pose3d> relativePose(const Pose3d & frame, const Pose3d & object) noexcept
{
  const auto frame_quaternion = normalized(frame);
  const auto object_quaternion = normalized(object);
  if (!isFinitePose(frame) || !isFinitePose(object) || !frame_quaternion || !object_quaternion) {
    return std::nullopt;
  }
  const Quaternion inverse{-frame_quaternion->x, -frame_quaternion->y, -frame_quaternion->z,
                           frame_quaternion->w};
  Pose3d result;
  rotate(inverse, object.x - frame.x, object.y - frame.y, object.z - frame.z, result.x, result.y,
         result.z);
  const Quaternion orientation = multiply(inverse, *object_quaternion);
  result.qx = orientation.x;
  result.qy = orientation.y;
  result.qz = orientation.z;
  result.qw = orientation.w;
  return result;
}

std::optional<Pose3d> composePose(const Pose3d & frame, const Pose3d & relative) noexcept
{
  const auto frame_quaternion = normalized(frame);
  const auto relative_quaternion = normalized(relative);
  if (!isFinitePose(frame) || !isFinitePose(relative) || !frame_quaternion ||
      !relative_quaternion) {
    return std::nullopt;
  }
  Pose3d result;
  rotate(*frame_quaternion, relative.x, relative.y, relative.z, result.x, result.y, result.z);
  result.x += frame.x;
  result.y += frame.y;
  result.z += frame.z;
  const Quaternion orientation = multiply(*frame_quaternion, *relative_quaternion);
  result.qx = orientation.x;
  result.qy = orientation.y;
  result.qz = orientation.z;
  result.qw = orientation.w;
  return result;
}

}  // namespace pick_place_common
