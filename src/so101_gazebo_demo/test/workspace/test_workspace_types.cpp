#include <gtest/gtest.h>

#include <chrono>
#include <cstdint>

#include "so101_gazebo_demo/workspace/workspace_types.hpp"

namespace ws = so101_gazebo_demo::workspace;

TEST(WorkspaceTypes, FullProfileMatchesApprovedDefaults)
{
  const auto config = ws::configForProfile(ws::WorkspaceProfile::FULL);
  EXPECT_EQ(config.time_budget, std::chrono::seconds(1800));
  EXPECT_EQ(config.batch_size, 25000U);
  EXPECT_EQ(config.minimum_samples, 250000U);
  EXPECT_EQ(config.maximum_samples, 2000000U);
  EXPECT_DOUBLE_EQ(config.position_voxel_size_m, 0.005);
  EXPECT_DOUBLE_EQ(config.orientation_threshold_rad, 0.17453292519943295);
  EXPECT_EQ(config.stable_batches, 5U);
  EXPECT_DOUBLE_EQ(config.position_new_rate_threshold, 0.001);
  EXPECT_DOUBLE_EQ(config.orientation_new_rate_threshold, 0.002);
}

TEST(WorkspaceTypes, RejectsSampleCountsOutsidePlyUint32Contract)
{
  auto config = ws::configForProfile(ws::WorkspaceProfile::FULL);
  config.maximum_samples = std::uint64_t{1} << 32;
  ASSERT_TRUE(ws::validateConfig(config));
  EXPECT_EQ(*ws::validateConfig(config), "maximum_samples must fit PLY uint32 sample_id");
}
