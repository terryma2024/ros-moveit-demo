#pragma once

#include <chrono>
#include <cstddef>
#include <deque>
#include <optional>

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

struct AttachmentExpectation
{
  bool gazebo_attached{false};
  bool moveit_attached{false};
};

[[nodiscard]] GripperEvidence gripperEvidence(const WorldSnapshot & snapshot);
[[nodiscard]] ValidationResult validateGripperOpen(
  const WorldSnapshot & snapshot, const GripperLimits & limits);
[[nodiscard]] ValidationResult validateGripperGrasp(
  const WorldSnapshot & snapshot, const GripperLimits & limits);
[[nodiscard]] ValidationResult validateAttachmentState(
  const WorldSnapshot & snapshot, bool gazebo_attached, bool moveit_attached);

class CokePoseStabilityTracker
{
public:
  CokePoseStabilityTracker(
    std::size_t required_samples = 5,
    double position_tolerance = 0.002,
    double orientation_tolerance_rad = 0.020);

  void addSample(
    const Pose3d & pose,
    std::chrono::steady_clock::time_point observed_at);
  [[nodiscard]] std::optional<bool> stationary() const noexcept;

private:
  struct Sample
  {
    Pose3d pose;
    std::chrono::steady_clock::time_point observed_at;
  };

  std::size_t required_samples_;
  double position_tolerance_;
  double orientation_tolerance_rad_;
  std::deque<Sample> samples_;
};

}  // namespace panda_gazebo_demo::pick_place
