#include "pick_place_common/checkpoint_validation.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

namespace pick_place_common
{

bool hasFiniteJointPositions(const std::map<std::string, double> & positions) noexcept
{
  return std::all_of(positions.begin(), positions.end(), [](const auto & item) {
    return !item.first.empty() && std::isfinite(item.second);
  });
}

bool hasFinitePoseMap(const std::map<std::string, Pose3d> & poses) noexcept
{
  return std::all_of(poses.begin(), poses.end(), [](const auto & item) {
    const auto & pose = item.second;
    return !item.first.empty() && std::isfinite(pose.x) && std::isfinite(pose.y) &&
           std::isfinite(pose.z) && std::isfinite(pose.qx) && std::isfinite(pose.qy) &&
           std::isfinite(pose.qz) && std::isfinite(pose.qw);
  });
}

NamedJointComparison compareNamedJointPositions(const std::map<std::string, double> & expected,
                                                const std::map<std::string, double> & actual,
                                                double tolerance) noexcept
{
  NamedJointComparison result{expected.size() == actual.size(), true, 0.0};
  if (!std::isfinite(tolerance) || tolerance < 0.0) {
    return {false, false, std::numeric_limits<double>::infinity()};
  }
  for (const auto & [name, expected_position] : expected) {
    const auto found = actual.find(name);
    if (name.empty() || found == actual.end() || !std::isfinite(expected_position) ||
        !std::isfinite(found->second)) {
      result.complete = false;
      result.within_tolerance = false;
      result.maximum_error = std::numeric_limits<double>::infinity();
      continue;
    }
    const double error = std::abs(expected_position - found->second);
    result.maximum_error = std::max(result.maximum_error, error);
    result.within_tolerance = result.within_tolerance && error <= tolerance;
  }
  if (!result.complete) {
    result.within_tolerance = false;
    result.maximum_error = std::numeric_limits<double>::infinity();
  }
  return result;
}

}  // namespace pick_place_common
