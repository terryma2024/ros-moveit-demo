#pragma once

#include <map>
#include <string>

#include "pick_place_common/pose_geometry.hpp"

namespace pick_place_common
{

struct NamedJointComparison
{
  bool complete;
  bool within_tolerance;
  double maximum_error;
};

[[nodiscard]] NamedJointComparison
compareNamedJointPositions(const std::map<std::string, double> & expected,
                           const std::map<std::string, double> & actual, double tolerance) noexcept;
[[nodiscard]] bool
hasFiniteJointPositions(const std::map<std::string, double> & positions) noexcept;
[[nodiscard]] bool hasFinitePoseMap(const std::map<std::string, Pose3d> & poses) noexcept;

}  // namespace pick_place_common
