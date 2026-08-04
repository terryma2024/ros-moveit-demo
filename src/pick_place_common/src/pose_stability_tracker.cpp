#include "pick_place_common/pose_stability_tracker.hpp"

namespace pick_place_common
{

PoseStabilityTracker::PoseStabilityTracker(std::size_t required_samples, double position_tolerance,
                                           double orientation_tolerance_rad) :
    required_samples_(required_samples), position_tolerance_(position_tolerance),
    orientation_tolerance_rad_(orientation_tolerance_rad)
{
}

void PoseStabilityTracker::addSample(const Pose3d & pose,
                                     std::chrono::steady_clock::time_point observed_at)
{
  samples_.push_back({pose, observed_at});
  while (samples_.size() > required_samples_) samples_.pop_front();
}

std::optional<bool> PoseStabilityTracker::stationary() const noexcept
{
  if (required_samples_ < 2 || samples_.size() < required_samples_) return std::nullopt;
  for (std::size_t index = 1; index < samples_.size(); ++index) {
    if (samples_[index].observed_at <= samples_[index - 1].observed_at ||
        positionDistance(samples_[index - 1].pose, samples_[index].pose) > position_tolerance_ ||
        orientationDistance(samples_[index - 1].pose, samples_[index].pose) >
          orientation_tolerance_rad_) {
      return false;
    }
  }
  return true;
}

}  // namespace pick_place_common
