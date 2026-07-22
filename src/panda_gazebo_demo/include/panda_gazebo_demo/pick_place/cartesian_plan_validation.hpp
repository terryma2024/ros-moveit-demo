#pragma once

#include <cstddef>
#include <vector>

#include "panda_gazebo_demo/pick_place/transition_contract.hpp"

namespace panda_gazebo_demo::pick_place
{

struct CartesianPlanEvidence
{
  double fraction{0.0};
  std::size_t trajectory_points{0};
  double max_joint_delta{0.0};
  bool time_parameterized{false};
  Pose3d start_tcp_pose;
  std::vector<Pose3d> tcp_path;
};

struct CartesianPlanLimits
{
  double min_fraction{0.99};
  double max_joint_delta{0.2};
  double max_lateral_deviation{0.02};
  double max_orientation_error_rad{0.1};
  double endpoint_position_tolerance{0.02};
  double endpoint_orientation_tolerance_rad{0.1};
};

[[nodiscard]] ValidationResult validateCartesianPlan(
  const CartesianPlanEvidence & evidence, const Pose3d & target,
  const CartesianPlanLimits & limits);

}  // namespace panda_gazebo_demo::pick_place
