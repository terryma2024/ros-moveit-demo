#include "so101_gazebo_demo/pick_place/calibration_cli_options.hpp"

#include <cmath>
#include <exception>

namespace so101_gazebo_demo::pick_place
{

CalibrationSearchParseResult
parseCalibrationSearchOptions(const std::vector<std::string> & arguments,
                              double default_gripper_q6)
{
  if (arguments.size() < 9 || arguments.size() > 11 || !std::isfinite(default_gripper_q6)) {
    return {std::nullopt, "search expects nine values plus optional seed_count and gripper_q6"};
  }
  CalibrationSearchOptions options;
  options.gripper_q6 = default_gripper_q6;
  try {
    for (std::size_t i = 0; i < options.values.size(); ++i) {
      std::size_t consumed = 0;
      options.values[i] = std::stod(arguments[i], &consumed);
      if (consumed != arguments[i].size() || !std::isfinite(options.values[i])) {
        return {std::nullopt, "search values must be finite numbers"};
      }
    }
    if (arguments.size() >= 10) {
      std::size_t consumed = 0;
      const auto parsed = std::stoull(arguments[9], &consumed);
      if (consumed != arguments[9].size() || parsed == 0) {
        return {std::nullopt, "seed_count must be a positive integer"};
      }
      options.seed_count = static_cast<std::size_t>(parsed);
    }
    if (arguments.size() == 11) {
      std::size_t consumed = 0;
      options.gripper_q6 = std::stod(arguments[10], &consumed);
      if (consumed != arguments[10].size() || !std::isfinite(options.gripper_q6)) {
        return {std::nullopt, "gripper_q6 must be finite"};
      }
    }
  } catch (const std::exception &) {
    return {std::nullopt, "search options contain an invalid number"};
  }
  return {options, {}};
}

}  // namespace so101_gazebo_demo::pick_place
