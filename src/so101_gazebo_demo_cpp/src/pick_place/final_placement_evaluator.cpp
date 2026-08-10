#include "so101_gazebo_demo/pick_place/final_placement_evaluator.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <utility>

namespace so101_gazebo_demo::pick_place
{
namespace
{

double uprightTilt(const Pose3d & pose)
{
  const double norm = std::hypot(std::hypot(pose.qx, pose.qy), std::hypot(pose.qz, pose.qw));
  if (!std::isfinite(norm) || norm <= 0.0)
    return std::numeric_limits<double>::infinity();
  const double qx = pose.qx / norm;
  const double qy = pose.qy / norm;
  const double rotated_z_z = 1.0 - 2.0 * (qx * qx + qy * qy);
  return std::acos(std::clamp(rotated_z_z, -1.0, 1.0));
}

bool inside(const Pose3d & pose, const AxisAlignedTargetRegion & region)
{
  return pose.x >= region.min_x && pose.x <= region.max_x && pose.y >= region.min_y &&
         pose.y <= region.max_y;
}

bool insideWorkspace(const Pose3d & pose, const std::array<double, 6> & bounds)
{
  return pose.x >= bounds[0] && pose.y >= bounds[1] && pose.z >= bounds[2] && pose.x <= bounds[3] &&
         pose.y <= bounds[4] && pose.z <= bounds[5];
}

std::string primaryFailureCode(const std::set<std::string> & violations)
{
  const std::pair<const char *, const char *> precedence[]{
    {"safety", "FINAL_PLACEMENT_SAFETY_FAILURE"},
    {"stale", "FINAL_PLACEMENT_EVIDENCE_STALE"},
    {"session_or_sequence", "FINAL_PLACEMENT_EVIDENCE_STALE"},
    {"gripper_contact", "FINAL_PLACEMENT_GRIPPER_CONTACT"},
    {"unsupported", "FINAL_PLACEMENT_UNSUPPORTED"},
    {"tipped", "FINAL_PLACEMENT_TIPPED"},
    {"still_moving", "FINAL_PLACEMENT_STILL_MOVING"},
    {"out_of_region", "FINAL_PLACEMENT_OUT_OF_REGION"}};
  for (const auto & [predicate, code] : precedence) {
    if (violations.count(predicate) != 0U)
      return code;
  }
  return "FINAL_PLACEMENT_EVIDENCE_STALE";
}

bool hasRequiredPolicy(const PhysicalOutcomePolicyConfig & policy)
{
  return policy.calibration_complete && policy.final_target_region &&
         policy.support_height_range_m && policy.max_upright_tilt_rad &&
         policy.max_linear_speed_m_s && policy.max_angular_speed_rad_s &&
         policy.consecutive_samples && policy.minimum_stable_duration_s &&
         policy.max_observation_age_s && policy.max_telemetry_samples &&
         policy.catastrophic_loss.workspace_bounds_m;
}

}  // namespace

FinalPlacementEvaluator::FinalPlacementEvaluator(PhysicalOutcomePolicyConfig policy) :
    policy_(std::move(policy))
{
}

FinalPlacementEvaluation
FinalPlacementEvaluator::evaluate(const ReleaseEpoch & epoch,
                                  const std::vector<WorldSnapshot> & snapshots) const
{
  FinalPlacementEvaluation result;
  result.metrics.observed_sample_count = snapshots.size();
  if (!hasRequiredPolicy(policy_)) {
    result.terminal_failure = true;
    result.metrics.violated_predicates.insert("safety");
    result.failure = Failure{FailureCategory::CONFIGURATION,
                             "FINAL_PLACEMENT_SAFETY_FAILURE",
                             "Final placement policy is not calibrated",
                             {}};
    return result;
  }

  std::optional<WorldSnapshot> previous;
  std::optional<std::chrono::steady_clock::time_point> window_start;
  std::uint64_t first_counted_sequence = 0;
  double linear_sum = 0.0;
  double angular_sum = 0.0;
  bool have_speed_aggregate = false;
  std::set<std::string> latest_violations;

  for (const auto & snapshot : snapshots) {
    if (snapshot.gazebo_pose_sequence && *snapshot.gazebo_pose_sequence <= epoch.start_sequence) {
      ++result.metrics.pre_release_rejected_count;
      continue;
    }
    ++result.metrics.post_release_sample_count;
    std::set<std::string> violations;
    if (snapshot.simulation_session_id != epoch.simulation_session_id)
      violations.insert("session_or_sequence");
    const bool structural = snapshot.gazebo_pose_sequence && snapshot.gazebo_pose_observed_at &&
                            snapshot.gazebo_task_object_pose_world &&
                            snapshot.simulation_session_id == epoch.simulation_session_id;
    if (!structural || !snapshot.fresh ||
        (snapshot.gazebo_task_object_pose_world &&
         !isFinitePose(*snapshot.gazebo_task_object_pose_world))) {
      violations.insert("stale");
    }
    if (previous && structural) {
      if (!previous->gazebo_pose_sequence || !previous->gazebo_pose_observed_at ||
          snapshot.simulation_session_id != previous->simulation_session_id ||
          *snapshot.gazebo_pose_sequence <= *previous->gazebo_pose_sequence ||
          *snapshot.gazebo_pose_observed_at <= *previous->gazebo_pose_observed_at) {
        violations.insert("session_or_sequence");
      }
    }

    FinalPlacementSample summary;
    if (structural) {
      summary.sequence = *snapshot.gazebo_pose_sequence;
      summary.pose = *snapshot.gazebo_task_object_pose_world;
      summary.upright_tilt_rad = uprightTilt(summary.pose);
      if (!insideWorkspace(summary.pose, *policy_.catastrophic_loss.workspace_bounds_m) ||
          snapshot.gazebo_task_object_attached.value_or(true) ||
          snapshot.moveit_task_object_attached.value_or(true)) {
        violations.insert("safety");
      }
      if (!inside(summary.pose, *policy_.final_target_region))
        violations.insert("out_of_region");
      if (summary.pose.z < (*policy_.support_height_range_m)[0] ||
          summary.pose.z > (*policy_.support_height_range_m)[1] ||
          !snapshot.gazebo_task_object_intended_support_contact.value_or(false)) {
        violations.insert("unsupported");
      }
      if (summary.upright_tilt_rad > *policy_.max_upright_tilt_rad)
        violations.insert("tipped");
      if (snapshot.gazebo_task_object_gripper_contact.value_or(true))
        violations.insert("gripper_contact");
      const auto pose_time = *snapshot.gazebo_pose_observed_at;
      const auto evidence_fresh = [&](const auto & observed_at) {
        return observed_at &&
               std::abs(std::chrono::duration<double>(pose_time - *observed_at).count()) <=
                 *policy_.max_observation_age_s;
      };
      if (!evidence_fresh(snapshot.gazebo_support_contact_observed_at) ||
          !evidence_fresh(snapshot.gazebo_gripper_contact_observed_at)) {
        violations.insert("stale");
      }
    }

    const bool adjacent = previous && structural && previous->gazebo_task_object_pose_world &&
                          previous->gazebo_pose_observed_at && previous->gazebo_pose_sequence &&
                          previous->simulation_session_id == snapshot.simulation_session_id &&
                          *snapshot.gazebo_pose_sequence > *previous->gazebo_pose_sequence &&
                          *snapshot.gazebo_pose_observed_at > *previous->gazebo_pose_observed_at;
    if (adjacent) {
      const double elapsed = std::chrono::duration<double>(*snapshot.gazebo_pose_observed_at -
                                                           *previous->gazebo_pose_observed_at)
                               .count();
      summary.linear_speed_m_s = positionDistance(*previous->gazebo_task_object_pose_world,
                                                  *snapshot.gazebo_task_object_pose_world) /
                                 elapsed;
      summary.angular_speed_rad_s = orientationDistance(*previous->gazebo_task_object_pose_world,
                                                        *snapshot.gazebo_task_object_pose_world) /
                                    elapsed;
      if (!std::isfinite(summary.linear_speed_m_s) || !std::isfinite(summary.angular_speed_rad_s)) {
        violations.insert("stale");
      } else {
        ++result.metrics.derived_speed_sample_count;
        linear_sum += summary.linear_speed_m_s;
        angular_sum += summary.angular_speed_rad_s;
        if (!have_speed_aggregate) {
          result.metrics.min_linear_speed_m_s = summary.linear_speed_m_s;
          result.metrics.max_linear_speed_m_s = summary.linear_speed_m_s;
          result.metrics.min_angular_speed_rad_s = summary.angular_speed_rad_s;
          result.metrics.max_angular_speed_rad_s = summary.angular_speed_rad_s;
          have_speed_aggregate = true;
        } else {
          result.metrics.min_linear_speed_m_s =
            std::min(result.metrics.min_linear_speed_m_s, summary.linear_speed_m_s);
          result.metrics.max_linear_speed_m_s =
            std::max(result.metrics.max_linear_speed_m_s, summary.linear_speed_m_s);
          result.metrics.min_angular_speed_rad_s =
            std::min(result.metrics.min_angular_speed_rad_s, summary.angular_speed_rad_s);
          result.metrics.max_angular_speed_rad_s =
            std::max(result.metrics.max_angular_speed_rad_s, summary.angular_speed_rad_s);
        }
        if (summary.linear_speed_m_s > *policy_.max_linear_speed_m_s ||
            summary.angular_speed_rad_s > *policy_.max_angular_speed_rad_s) {
          violations.insert("still_moving");
        }
      }
      if (result.metrics.retained_samples.size() < *policy_.max_telemetry_samples) {
        summary.violated_predicates = violations;
        result.metrics.retained_samples.push_back(summary);
      }
    } else {
      violations.insert("stale");
    }

    result.metrics.violated_predicates.insert(violations.begin(), violations.end());
    latest_violations = violations;
    if (violations.empty()) {
      if (result.metrics.consecutive_samples == 0U) {
        window_start = snapshot.gazebo_pose_observed_at;
        first_counted_sequence = *snapshot.gazebo_pose_sequence;
      }
      ++result.metrics.consecutive_samples;
      result.metrics.consecutive_duration_s =
        std::chrono::duration<double>(*snapshot.gazebo_pose_observed_at - *window_start).count();
      if (result.metrics.consecutive_samples >= *policy_.consecutive_samples &&
          result.metrics.consecutive_duration_s >= *policy_.minimum_stable_duration_s) {
        result.stable = true;
        result.evidence = FinalPlacementEvidence{epoch,
                                                 first_counted_sequence,
                                                 *snapshot.gazebo_pose_sequence,
                                                 summary.pose,
                                                 result.metrics.consecutive_samples,
                                                 result.metrics.consecutive_duration_s};
      }
    } else {
      result.metrics.consecutive_samples = 0;
      result.metrics.consecutive_duration_s = 0.0;
      window_start.reset();
      result.evidence.reset();
      result.stable = false;
    }
    previous = structural ? std::optional<WorldSnapshot>{snapshot} : std::nullopt;
  }

  if (result.metrics.derived_speed_sample_count != 0U) {
    result.metrics.mean_linear_speed_m_s =
      linear_sum / static_cast<double>(result.metrics.derived_speed_sample_count);
    result.metrics.mean_angular_speed_rad_s =
      angular_sum / static_cast<double>(result.metrics.derived_speed_sample_count);
  }
  if (!result.stable) {
    const auto code = primaryFailureCode(latest_violations);
    result.terminal_failure = code == "FINAL_PLACEMENT_SAFETY_FAILURE";
    result.failure = Failure{FailureCategory::POSTCONDITION,
                             code,
                             "Final physical placement has not reached a stable valid outcome",
                             {}};
  }
  return result;
}

}  // namespace so101_gazebo_demo::pick_place
