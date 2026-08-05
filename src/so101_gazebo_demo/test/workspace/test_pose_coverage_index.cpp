#include <gtest/gtest.h>

#include <cmath>

#include "so101_gazebo_demo/workspace/pose_coverage_index.hpp"

namespace ws = so101_gazebo_demo::workspace;

namespace
{
constexpr double radians(double degrees)
{
  return degrees * 3.14159265358979323846 / 180.0;
}

ws::PoseSample sampleAt(double x, double y, double z, std::array<double, 4> quaternion,
                        bool collision_free = true)
{
  ws::PoseSample sample{};
  sample.sample_id = 1;
  sample.tcp_pose = {x, y, z, quaternion[0], quaternion[1], quaternion[2], quaternion[3]};
  sample.bounds_valid = true;
  sample.collision_free = collision_free;
  return sample;
}
}  // namespace

TEST(PoseCoverageIndex, UsesFloorForNegativeWorldCoordinates)
{
  ws::PoseCoverageIndex index(0.005, radians(10.0));
  EXPECT_EQ(index.keyFor({-0.0001, 0.0049, -0.0051}), (ws::PositionVoxelKey{-1, 0, -2}));
}

TEST(PoseCoverageIndex, QuaternionSignDoesNotCreateASecondOrientation)
{
  ws::PoseCoverageIndex index(0.005, radians(10.0));
  auto first = sampleAt(0.1, 0.2, 0.3, {0.0, 0.0, 0.0, 1.0});
  auto second = sampleAt(0.1, 0.2, 0.3, {0.0, 0.0, 0.0, -1.0});
  second.sample_id = 2;
  index.insert(first);
  index.insert(second);
  EXPECT_EQ(first.orientation_cluster_id, second.orientation_cluster_id);
  EXPECT_EQ(index.voxelSummaries().front().orientation_count, 1U);
}

TEST(PoseCoverageIndex, SeparatesOrientationsOutsideThresholdAndCountsFreeSubset)
{
  ws::PoseCoverageIndex index(0.005, radians(10.0));
  auto first = sampleAt(0.1, 0.2, 0.3, {0.0, 0.0, 0.0, 1.0});
  auto second =
    sampleAt(0.1, 0.2, 0.3, {0.0, 0.0, std::sin(radians(6.0)), std::cos(radians(6.0))}, false);
  second.sample_id = 2;
  index.insert(first);
  index.insert(second);
  const auto summary = index.voxelSummaries().front();
  EXPECT_EQ(summary.orientation_count, 2U);
  EXPECT_EQ(summary.collision_free_orientation_count, 1U);
  EXPECT_EQ(summary.collision_free_count, 1U);
}

TEST(PoseCoverageIndex, FinishBatchReportsPriorCoverage)
{
  ws::PoseCoverageIndex index(0.005, radians(10.0));
  auto first = sampleAt(0.1, 0.2, 0.3, {0.0, 0.0, 0.0, 1.0});
  index.insert(first);
  const auto first_delta = index.finishBatch();
  EXPECT_EQ(first_delta.new_position_voxels, 1U);
  EXPECT_EQ(first_delta.existing_position_voxels_before_batch, 0U);
  auto second = sampleAt(0.1, 0.2, 0.3, {0.0, 0.0, 0.0, 1.0});
  index.insert(second);
  const auto second_delta = index.finishBatch();
  EXPECT_EQ(second_delta.new_position_voxels, 0U);
  EXPECT_EQ(second_delta.existing_position_voxels_before_batch, 1U);
}

TEST(PoseCoverageIndex, CheckpointRestoresClusterIdentity)
{
  ws::PoseCoverageIndex first(0.005, radians(10.0));
  auto sample = sampleAt(0.1, 0.2, 0.3, {0.0, 0.0, 0.0, 1.0});
  first.insert(sample);
  ws::PoseCoverageIndex resumed(0.005, radians(10.0));
  resumed.restore(first.checkpoint());
  auto duplicate = sampleAt(0.1, 0.2, 0.3, {0.0, 0.0, 0.0, -1.0});
  resumed.insert(duplicate);
  EXPECT_EQ(duplicate.orientation_cluster_id, 0U);
  EXPECT_EQ(resumed.voxelSummaries().front().orientation_count, 1U);
}

TEST(PoseCoverageIndex, RequiresBothRatesToStayLowForFiveBatches)
{
  auto config = ws::configForProfile(ws::WorkspaceProfile::FULL);
  ws::ConvergenceTracker tracker(config);
  for (int batch = 0; batch < 4; ++batch) {
    EXPECT_FALSE(tracker.observe({1, 1, 10000, 10000}, 300000 + batch * 25000));
  }
  EXPECT_TRUE(tracker.observe({1, 1, 10000, 10000}, 400000));
}

TEST(PoseCoverageIndex, ConvergenceCannotOccurBeforeMinimumSamples)
{
  auto config = ws::configForProfile(ws::WorkspaceProfile::FULL);
  ws::ConvergenceTracker tracker(config);
  for (int batch = 0; batch < 8; ++batch) {
    EXPECT_FALSE(tracker.observe({0, 0, 10000, 10000}, 100000));
  }
  EXPECT_EQ(tracker.consecutiveStableBatches(), 0U);
}
