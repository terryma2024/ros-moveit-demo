#pragma once

#include <chrono>
#include <cstddef>
#include <deque>
#include <optional>

#include "pick_place_common/pose_geometry.hpp"

namespace pick_place_common
{

class PoseStabilityTracker
{
public:
  PoseStabilityTracker(std::size_t required_samples, double position_tolerance,
                       double orientation_tolerance_rad);
  void addSample(const Pose3d &, std::chrono::steady_clock::time_point);
  [[nodiscard]] std::optional<bool> stationary() const noexcept;

private:
  struct Sample
  {
    Pose3d pose;
    std::chrono::steady_clock::time_point observed_at;
  };

  std::size_t required_samples_;
  double position_tolerance_;
  double orientation_tolerance_rad_;
  std::deque<Sample> samples_;
};

}  // namespace pick_place_common
