#include <string>
#include <vector>

#include <gtest/gtest.h>

#include "so101_gazebo_demo/pick_place/calibration_cli_options.hpp"

namespace spp = so101_gazebo_demo::pick_place;

TEST(CalibrationCliOptions, ParsesNineRequiredSearchValuesWithDefaults)
{
  const std::vector<std::string> args{"0.02", "-0.28", "0.222", "0", "0", "-1", "0", "0", "-1"};
  const auto result = spp::parseCalibrationSearchOptions(args, 0.707194871);
  ASSERT_TRUE(result.options);
  EXPECT_EQ(result.options->seed_count, 4096U);
  EXPECT_DOUBLE_EQ(result.options->gripper_q6, 0.707194871);
}

TEST(CalibrationCliOptions, ParsesSeedThenGripperQ6WithoutOffByOne)
{
  const std::vector<std::string> args{"0.02", "-0.28", "0.222", "0",   "0",  "-1",
                                      "0",    "0",     "-1",    "512", "0.9"};
  const auto result = spp::parseCalibrationSearchOptions(args, 0.707194871);
  ASSERT_TRUE(result.options);
  EXPECT_EQ(result.options->seed_count, 512U);
  EXPECT_DOUBLE_EQ(result.options->gripper_q6, 0.9);
  EXPECT_DOUBLE_EQ(result.options->values[8], -1.0);
}

TEST(CalibrationCliOptions, RejectsWrongArityOrZeroSeedCount)
{
  EXPECT_FALSE(spp::parseCalibrationSearchOptions({"1", "2"}, 0.7).options);
  const std::vector<std::string> zero_seed{"0", "0", "0", "0", "0", "-1", "0", "0", "-1", "0"};
  EXPECT_FALSE(spp::parseCalibrationSearchOptions(zero_seed, 0.7).options);
}
