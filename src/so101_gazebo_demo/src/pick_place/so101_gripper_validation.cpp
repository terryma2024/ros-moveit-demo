#include "so101_gazebo_demo/pick_place/so101_gripper_validation.hpp"

#include <cmath>
#include <limits>
#include <utility>

namespace so101_gazebo_demo::pick_place
{

double gripperWidthAtSection(double q6, const SO101Profile & profile)
{
  const double q_span = profile.q6_preopen - profile.q6_contact;
  if (!std::isfinite(q6) || !std::isfinite(q_span) || std::abs(q_span) < 1e-12) {
    return std::numeric_limits<double>::quiet_NaN();
  }
  return profile.contact_width +
         (q6 - profile.q6_contact) * (profile.preopen_width - profile.contact_width) / q_span;
}

ValidationResult validateQ6Target(const WorldSnapshot & snapshot, double target_q6,
                                  double target_width, const SO101Profile & profile)
{
  ValidationResult result{true, {}, {}};
  const auto position = snapshot.joint_positions.find(profile.gripper_joint);
  const auto velocity = snapshot.joint_velocities.find(profile.gripper_joint);
  if (!snapshot.fresh || position == snapshot.joint_positions.end() ||
      velocity == snapshot.joint_velocities.end() || !std::isfinite(position->second) ||
      !std::isfinite(velocity->second)) {
    return {false,
            {{FailureCategory::GRIPPER,
              "Q6_EVIDENCE_INCOMPLETE",
              "Fresh finite joint 6 position and velocity are required",
              {}}},
            {}};
  }
  const auto width = gripperWidthAtSection(position->second, profile);
  result.metrics = {{"q6", position->second},
                    {"q6_velocity", velocity->second},
                    {"section_depth", profile.grasp_section_depth},
                    {"gripper_width", width}};
  if (!std::isfinite(target_q6) || std::abs(position->second - target_q6) > profile.q6_tolerance) {
    result.failures.push_back({FailureCategory::GRIPPER,
                               "Q6_TARGET_OUT_OF_TOLERANCE",
                               "Joint 6 is outside the configured target tolerance",
                               {}});
  }
  if (!std::isfinite(width) || !std::isfinite(target_width) ||
      std::abs(width - target_width) > profile.width_tolerance) {
    result.failures.push_back({FailureCategory::GRIPPER,
                               "Q6_WIDTH_OUT_OF_TOLERANCE",
                               "Joint 6 does not produce the required 20 mm-section width",
                               {}});
  }
  if (std::abs(velocity->second) > profile.q6_velocity_tolerance) {
    result.failures.push_back({FailureCategory::GRIPPER,
                               "Q6_NOT_STATIONARY",
                               "Joint 6 velocity exceeds the stop threshold",
                               {}});
  }
  result.ok = result.failures.empty();
  return result;
}

}  // namespace so101_gazebo_demo::pick_place
