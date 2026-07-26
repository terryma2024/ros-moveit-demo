#pragma once

#include <array>
#include <cstddef>
#include <optional>
#include <string>
#include <vector>

namespace so101_gazebo_demo::pick_place
{

struct CalibrationSearchOptions
{
  std::array<double, 9> values{};
  std::size_t seed_count{4096};
  double gripper_q6{0.0};
};

struct CalibrationSearchParseResult
{
  std::optional<CalibrationSearchOptions> options;
  std::string error;
};

[[nodiscard]] CalibrationSearchParseResult
parseCalibrationSearchOptions(const std::vector<std::string> & arguments,
                              double default_gripper_q6);

}  // namespace so101_gazebo_demo::pick_place
