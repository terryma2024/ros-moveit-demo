#pragma once

#include <optional>

namespace pick_place_common
{

struct Pose3d
{
  double x{0};
  double y{0};
  double z{0};
  double qx{0};
  double qy{0};
  double qz{0};
  double qw{1};
};

[[nodiscard]] bool isFinitePose(const Pose3d &) noexcept;
[[nodiscard]] bool hasUsableQuaternion(const Pose3d &,
                                       double minimum_squared_norm = 1e-24) noexcept;
[[nodiscard]] double positionDistance(const Pose3d &, const Pose3d &) noexcept;
[[nodiscard]] double orientationDistance(const Pose3d &, const Pose3d &) noexcept;
[[nodiscard]] std::optional<Pose3d> relativePose(const Pose3d & frame,
                                                 const Pose3d & object) noexcept;
[[nodiscard]] std::optional<Pose3d> composePose(const Pose3d & frame,
                                                const Pose3d & relative) noexcept;

}  // namespace pick_place_common
