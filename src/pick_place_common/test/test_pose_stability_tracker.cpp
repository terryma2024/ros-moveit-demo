#include <gtest/gtest.h>

#include <chrono>
#include <cmath>

#include "pick_place_common/pose_stability_tracker.hpp"

namespace pick_place_common
{
namespace
{

using Clock = std::chrono::steady_clock;
constexpr Pose3d kPose{0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0};

TEST(PoseStabilityTracker, NeedsAllSamples)
{
  PoseStabilityTracker tracker(3, 0.01, 0.1);
  tracker.addSample(kPose, Clock::time_point{});
  tracker.addSample(kPose, Clock::time_point{} + std::chrono::seconds(1));
  EXPECT_FALSE(tracker.stationary().has_value());
}

TEST(PoseStabilityTracker, RejectsEqualOrReverseTimestamps)
{
  for (const auto second : {Clock::time_point{}, Clock::time_point{} - std::chrono::seconds(1)}) {
    PoseStabilityTracker tracker(2, 0.01, 0.1);
    tracker.addSample(kPose, Clock::time_point{});
    tracker.addSample(kPose, second);
    ASSERT_TRUE(tracker.stationary().has_value());
    EXPECT_FALSE(*tracker.stationary());
  }
}

TEST(PoseStabilityTracker, IncludesToleranceBoundaryAndRejectsJustOver)
{
  Pose3d at_position = kPose;
  at_position.x = 0.01;
  PoseStabilityTracker position_at(2, 0.01, 0.1);
  position_at.addSample(kPose, Clock::time_point{});
  position_at.addSample(at_position, Clock::time_point{} + std::chrono::seconds(1));
  EXPECT_TRUE(*position_at.stationary());

  PoseStabilityTracker position_over(2, 0.01, 0.1);
  at_position.x = std::nextafter(0.01, 1.0);
  position_over.addSample(kPose, Clock::time_point{});
  position_over.addSample(at_position, Clock::time_point{} + std::chrono::seconds(1));
  EXPECT_FALSE(*position_over.stationary());

  Pose3d at_angle = kPose;
  at_angle.qz = std::sin(0.05);
  at_angle.qw = std::cos(0.05);
  PoseStabilityTracker angle_at(2, 0.01, 0.1);
  angle_at.addSample(kPose, Clock::time_point{});
  angle_at.addSample(at_angle, Clock::time_point{} + std::chrono::seconds(1));
  EXPECT_TRUE(*angle_at.stationary());

  PoseStabilityTracker angle_over(2, 0.01, 0.1);
  const double over = 0.100001;
  at_angle.qz = std::sin(over / 2.0);
  at_angle.qw = std::cos(over / 2.0);
  angle_over.addSample(kPose, Clock::time_point{});
  angle_over.addSample(at_angle, Clock::time_point{} + std::chrono::seconds(1));
  EXPECT_FALSE(*angle_over.stationary());
}

TEST(PoseStabilityTracker, InvalidPoseIsNotStationary)
{
  Pose3d invalid = kPose;
  invalid.qw = 0.0;
  PoseStabilityTracker tracker(2, 0.01, 0.1);
  tracker.addSample(kPose, Clock::time_point{});
  tracker.addSample(invalid, Clock::time_point{} + std::chrono::seconds(1));
  EXPECT_FALSE(*tracker.stationary());
}

}  // namespace
}  // namespace pick_place_common
