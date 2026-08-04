#include <gtest/gtest.h>

#include <cmath>
#include <chrono>

#include "pick_place_common/pose_stability_tracker.hpp"
#include "so101_gazebo_demo/pick_place/support_pose.hpp"

namespace spp = so101_gazebo_demo::pick_place;

TEST(SupportPose, DistinguishesPickAndPlaceSupports)
{
  spp::SO101Profile profile;
  profile.task_object_pose = {0.1, 0.2, 0.3, 0.0, 0.0, 0.0, 1.0};
  profile.place_task_object_pose = {0.4, 0.5, 0.3, 0.0, 0.0, 0.0, 1.0};
  profile.task_object_position_drift_tolerance = 0.01;
  profile.place_support_xy_tolerance = 0.01;
  profile.place_support_height_tolerance = 0.01;
  profile.place_support_tilt_tolerance_rad = 0.1;

  EXPECT_TRUE(spp::supportedAtPick(profile.task_object_pose, profile));
  EXPECT_FALSE(spp::supportedAtPlace(profile.task_object_pose, profile));
  EXPECT_TRUE(spp::supportedAtPlace(profile.place_task_object_pose, profile));
  EXPECT_FALSE(spp::supportedAtPick(profile.place_task_object_pose, profile));
}

TEST(SupportPose, RejectsInvalidAndTiltedPoses)
{
  spp::SO101Profile profile;
  profile.task_object_pose = {0.1, 0.2, 0.3, 0.0, 0.0, 0.0, 1.0};
  profile.place_task_object_pose = profile.task_object_pose;
  profile.task_object_position_drift_tolerance = 0.01;
  profile.place_support_xy_tolerance = 0.01;
  profile.place_support_height_tolerance = 0.01;
  profile.place_support_tilt_tolerance_rad = 0.1;

  auto invalid = profile.task_object_pose;
  invalid.qw = 0.0;
  EXPECT_FALSE(spp::supportedAtPick(invalid, profile));
  EXPECT_FALSE(spp::supportedAtPlace(invalid, profile));

  auto tilted = profile.task_object_pose;
  tilted.qx = std::sin(0.1);
  tilted.qw = std::cos(0.1);
  EXPECT_FALSE(spp::supportedAtPick(tilted, profile));
  EXPECT_FALSE(spp::supportedAtPlace(tilted, profile));
}

TEST(SO101PoseStability, PreservesValidJitterAndOutOfOrderBehavior)
{
  pick_place_common::PoseStabilityTracker tracker(3, 0.002, 0.02);
  const auto start = std::chrono::steady_clock::now();
  tracker.addSample({0.1, 0.2, 0.3, 0.0, 0.0, 0.0, 1.0}, start);
  tracker.addSample({0.101, 0.2, 0.3, 0.0, 0.0, 0.0, 1.0}, start + std::chrono::milliseconds(10));
  tracker.addSample({0.1015, 0.2, 0.3, 0.0, 0.0, 0.0, 1.0}, start + std::chrono::milliseconds(20));
  ASSERT_TRUE(tracker.stationary());
  EXPECT_TRUE(*tracker.stationary());

  tracker.addSample({0.1, 0.2, 0.3, 0.0, 0.0, 0.0, 1.0}, start + std::chrono::milliseconds(15));
  ASSERT_TRUE(tracker.stationary());
  EXPECT_FALSE(*tracker.stationary());
}
