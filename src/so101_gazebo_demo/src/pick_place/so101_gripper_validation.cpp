#include "so101_gazebo_demo/pick_place/so101_gripper_validation.hpp"

#include <algorithm>
#include <cmath>
#include <iterator>
#include <limits>
#include <utility>

#include "so101_gazebo_demo/pick_place/gripper_width_calibration_data.hpp"
#include "so101_gazebo_demo/pick_place/fingertip_pad_gap_calibration_data.hpp"

namespace so101_gazebo_demo::pick_place
{

double gripperWidthAtSection(double q6, const SO101Profile & profile)
{
  namespace calibration = gripper_calibration;
  // Bullet Featherstone's position interface can settle just beyond a commanded
  // endpoint. Clamp only values that remain inside the profile's independently
  // validated q6 tolerance; never extrapolate the mesh-derived table.
  const double calibration_endpoint_tolerance = profile.q6_tolerance;
  if (!std::isfinite(q6) ||
      profile.gripper_geometry_model_version != calibration::kModelVersion ||
      profile.gripper_geometry_model_fingerprint != calibration::kModelFingerprint ||
      std::abs(profile.grasp_section_depth - calibration::kGraspDepth) > 1e-12 ||
      q6 < calibration::kSamples.front().q6 - calibration_endpoint_tolerance ||
      q6 > calibration::kSamples.back().q6 + calibration_endpoint_tolerance) {
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

double fingertipPadMinimumGapAtQ6(double q6, const SO101Profile & profile)
{
  namespace calibration = fingertip_pad_calibration;
  if (!std::isfinite(q6) ||
      profile.fingertip_pad_calibration_fingerprint != calibration::kInputFingerprint ||
      q6 < calibration::kGapSamples.front().q6 || q6 > calibration::kGapSamples.back().q6) {
    return std::numeric_limits<double>::quiet_NaN();
  }
  const auto upper = std::lower_bound(
    calibration::kGapSamples.begin(), calibration::kGapSamples.end(), q6,
    [](const calibration::GapSample & sample, double value) { return sample.q6 < value; });
  if (upper == calibration::kGapSamples.begin()) return upper->minimum_pad_gap_m;
  if (upper == calibration::kGapSamples.end()) return calibration::kGapSamples.back().minimum_pad_gap_m;
  const auto lower = std::prev(upper);
  const double ratio = (q6 - lower->q6) / (upper->q6 - lower->q6);
  return lower->minimum_pad_gap_m +
         ratio * (upper->minimum_pad_gap_m - lower->minimum_pad_gap_m);
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
  namespace pad_calibration = fingertip_pad_calibration;
  const auto width = gripperWidthAtSection(position->second, profile);
  const bool native_pad_grasp = std::abs(target_q6 - pad_calibration::kGraspQ6) <= 1e-12;
  const bool native_pad_preopen = std::abs(target_q6 - pad_calibration::kPreopenQ6) <= 1e-12;
  const bool native_pad_target = native_pad_grasp || native_pad_preopen;
  const bool full_open_target = std::abs(target_q6 - profile.q6_full_open) <= 1e-12;
  const bool native_pad_calibration_matches =
    profile.fingertip_pad_calibration_fingerprint == pad_calibration::kInputFingerprint;
  const bool bounded_contact_stop = native_pad_grasp &&
    snapshot.gazebo_task_object_gripper_contact &&
    snapshot.gazebo_task_object_gripper_max_depth &&
    std::isfinite(*snapshot.gazebo_task_object_gripper_max_depth) &&
    *snapshot.gazebo_task_object_gripper_max_depth <= profile.max_gripper_contact_depth;
  const double expected_pad_gap = native_pad_grasp ? pad_calibration::kGraspGapM :
    pad_calibration::kPreopenGapM;
  const double actual_pad_gap = native_pad_target && native_pad_calibration_matches
    ? fingertipPadMinimumGapAtQ6(position->second, profile)
    : std::numeric_limits<double>::quiet_NaN();
  const double actual_wall_interference = std::isfinite(actual_pad_gap)
    ? std::max(0.0, profile.task_object_wall_thickness - actual_pad_gap)
    : std::numeric_limits<double>::quiet_NaN();
  result.metrics = {{"expected_q6", target_q6},
                    {"actual_q6", position->second},
                    {"actual_q6_velocity", velocity->second},
                    {"section_depth", profile.grasp_section_depth},
                    {"expected_gripper_width", target_width},
                    {"actual_gripper_width", width},
                    {"expected_pad_gap_m", native_pad_target ? expected_pad_gap : std::numeric_limits<double>::quiet_NaN()},
                    {"actual_pad_gap_m", actual_pad_gap},
                    {"actual_wall_interference_m", actual_wall_interference}};
  const double target_tolerance = full_open_target ? profile.q6_full_open_tolerance :
    (native_pad_grasp ? profile.contact_q6_stop_tolerance : profile.q6_tolerance);
  if (!std::isfinite(target_q6) ||
      (std::abs(position->second - target_q6) > target_tolerance && !bounded_contact_stop)) {
    result.failures.push_back({FailureCategory::GRIPPER,
                               "Q6_TARGET_OUT_OF_TOLERANCE",
                               "Joint 6 is outside the configured target tolerance",
                               {}});
  }
  const bool geometry_model_matches =
    profile.gripper_geometry_model_version == gripper_calibration::kModelVersion &&
    profile.gripper_geometry_model_fingerprint == gripper_calibration::kModelFingerprint &&
    std::abs(profile.grasp_section_depth - gripper_calibration::kGraspDepth) <= 1e-12;
  if (native_pad_target && !native_pad_calibration_matches) {
    result.failures.push_back({FailureCategory::GRIPPER,
                               "Q6_NATIVE_PAD_CALIBRATION_MISMATCH",
                               "Runtime fingertip-pad policy fingerprint does not match the generated calibration",
                               {}});
  } else if (native_pad_target &&
             (!std::isfinite(actual_pad_gap) ||
              position->second < pad_calibration::kSafeFloorQ6 -
                pad_calibration::kControllerEndpointEpsilonRad ||
              actual_pad_gap < pad_calibration::kSafeFloorGapM)) {
    result.failures.push_back({FailureCategory::GRIPPER,
                               "Q6_NATIVE_PAD_SAFE_FLOOR_VIOLATED",
                               "Observed joint 6 is below the generated native-pad safe floor or clearance",
                               {}});
  } else if (native_pad_grasp &&
             (!std::isfinite(actual_wall_interference) ||
              actual_wall_interference > pad_calibration::kCupWallInterferenceM + 1e-12)) {
    result.failures.push_back({FailureCategory::GRIPPER,
                               "Q6_NATIVE_PAD_INTERFERENCE_EXCEEDED",
                               "Observed native-pad gap exceeds the cup-wall interference ceiling",
                               {}});
  } else if (!geometry_model_matches && !native_pad_target && !full_open_target) {
    result.failures.push_back({FailureCategory::GRIPPER,
                               "Q6_GEOMETRY_MODEL_MISMATCH",
                               "The q6 width calibration does not match the configured mesh/URDF model",
                               {}});
  } else if (native_pad_target &&
             (!std::isfinite(actual_pad_gap) || std::abs(target_width - expected_pad_gap) > 1e-12)) {
    result.failures.push_back({FailureCategory::GRIPPER,
                               "Q6_NATIVE_PAD_GAP_OUT_OF_TOLERANCE",
                               "Native fingertip-pad grasp does not match the fingerprint-bound gap calibration",
                               {}});
  } else if (!native_pad_target && !full_open_target &&
             (!std::isfinite(width) || !std::isfinite(target_width) ||
             std::abs(width - target_width) > profile.width_tolerance)) {
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
