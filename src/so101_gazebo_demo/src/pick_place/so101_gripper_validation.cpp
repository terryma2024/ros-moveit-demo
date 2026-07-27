#include "so101_gazebo_demo/pick_place/so101_gripper_validation.hpp"

#include <algorithm>
#include <cmath>
#include <iterator>
#include <limits>
#include <utility>

#include "so101_gazebo_demo/pick_place/gripper_width_calibration_data.hpp"

namespace so101_gazebo_demo::pick_place
{

double gripperWidthAtSection(double q6, const SO101Profile & profile)
{
  namespace calibration = gripper_calibration;
  constexpr double kCalibrationEndpointEpsilon = 1e-9;
  if (!std::isfinite(q6) ||
      profile.gripper_geometry_model_version != calibration::kModelVersion ||
      profile.gripper_geometry_model_fingerprint != calibration::kModelFingerprint ||
      std::abs(profile.grasp_section_depth - calibration::kGraspDepth) > 1e-12 ||
      std::abs(profile.coke_radius * 2.0 - calibration::kCokeDiameter) > 1e-12 ||
      q6 < calibration::kSamples.front().q6 - kCalibrationEndpointEpsilon ||
      q6 > calibration::kSamples.back().q6 + kCalibrationEndpointEpsilon) {
    return std::numeric_limits<double>::quiet_NaN();
  }
  q6 = std::clamp(q6, calibration::kSamples.front().q6,
                  calibration::kSamples.back().q6);
  const auto upper = std::lower_bound(
    calibration::kSamples.begin(), calibration::kSamples.end(), q6,
    [](const calibration::CalibrationSample & sample, double value) {
      return sample.q6 < value;
    });
  if (upper == calibration::kSamples.begin()) {
    return upper->width;
  }
  if (upper == calibration::kSamples.end()) {
    return calibration::kSamples.back().width;
  }
  const auto lower = std::prev(upper);
  const auto ratio = (q6 - lower->q6) / (upper->q6 - lower->q6);
  return lower->width + ratio * (upper->width - lower->width);
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
  const bool geometry_model_matches =
    profile.gripper_geometry_model_version == gripper_calibration::kModelVersion &&
    profile.gripper_geometry_model_fingerprint == gripper_calibration::kModelFingerprint &&
    std::abs(profile.grasp_section_depth - gripper_calibration::kGraspDepth) <= 1e-12 &&
    std::abs(profile.coke_radius * 2.0 - gripper_calibration::kCokeDiameter) <= 1e-12;
  if (!geometry_model_matches) {
    result.failures.push_back({FailureCategory::GRIPPER,
                               "Q6_GEOMETRY_MODEL_MISMATCH",
                               "The q6 width calibration does not match the configured mesh/URDF model",
                               {}});
  } else if (!std::isfinite(width) || !std::isfinite(target_width) ||
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
