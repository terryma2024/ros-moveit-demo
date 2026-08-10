#pragma once

#include <chrono>
#include <cstddef>
#include <optional>

#include "pick_place_common/pose_stability_tracker.hpp"
#include "panda_gazebo_demo/pick_place/transition_contract.hpp"

namespace panda_gazebo_demo::pick_place
{

struct GripperLimits
{
  double open_min{0.038};
  double grasp_min{0.028};
  double grasp_max{0.037};
  double symmetry_tolerance{0.003};
  double velocity_tolerance{0.010};
};

struct GripperEvidence
{
  std::optional<double> finger1_position;
  std::optional<double> finger2_position;
  std::optional<double> finger1_velocity;
  std::optional<double> finger2_velocity;
};

[[nodiscard]] GripperEvidence gripperEvidence(const WorldSnapshot & snapshot);
[[nodiscard]] ValidationResult validateGripperOpen(const WorldSnapshot & snapshot,
                                                   const GripperLimits & limits);
[[nodiscard]] ValidationResult validateGripperGrasp(const WorldSnapshot & snapshot,
                                                    const GripperLimits & limits);
[[nodiscard]] ValidationResult validateGripperClosed(const WorldSnapshot & snapshot,
                                                     double target_position, double tolerance,
                                                     const GripperLimits & limits);
[[nodiscard]] ValidationResult validateAttachmentState(const WorldSnapshot & snapshot,
                                                       bool gazebo_attached, bool moveit_attached);

using CokePoseStabilityTracker = pick_place_common::PoseStabilityTracker;

}  // namespace panda_gazebo_demo::pick_place
