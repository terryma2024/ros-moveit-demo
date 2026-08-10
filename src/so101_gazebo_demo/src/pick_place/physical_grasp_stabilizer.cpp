#include "so101_gazebo_demo/pick_place/physical_grasp_stabilizer.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <thread>
#include <utility>

namespace so101_gazebo_demo::pick_place
{
namespace
{
constexpr double kMinimumTargetPenetrationM = 0.0001;
constexpr double kMaximumTargetPenetrationM = 0.001;
constexpr double kNormalizationStepQ6 = 0.001;
constexpr int kMaximumNormalizationAdjustments = 4;
}  // namespace

SO101PhysicalGraspStabilizer::SO101PhysicalGraspStabilizer(
  std::shared_ptr<IWorldObserver> observer, std::shared_ptr<IPhysicalGraspEvidenceStore> evidence,
  std::shared_ptr<ISO101GripperCommand> gripper, SO101Profile profile) :
    observer_(std::move(observer)), evidence_(std::move(evidence)), gripper_(std::move(gripper)),
    profile_(std::move(profile))
{
}

ActionResult SO101PhysicalGraspStabilizer::captureBeforeLift()
{
  return capture(true);
}

ActionResult SO101PhysicalGraspStabilizer::captureAfterLift()
{
  return capture(false);
}

ActionResult
SO101PhysicalGraspStabilizer::cancel()  // NOLINT(readability-convert-member-functions-to-static)
{
  cancelled_.store(true);
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ActionResult SO101PhysicalGraspStabilizer::capture(bool before_lift)
{
  const auto cancelled = [this]() -> std::optional<ActionResult> {
    if (!cancelled_.exchange(false))
      return std::nullopt;
    return ActionResult{ActionStatus::FAILED,
                        Failure{FailureCategory::EXECUTION,
                                "PHYSICAL_GRASP_STABILIZATION_CANCELLED",
                                "Physical-grasp stability capture was cancelled",
                                {}}};
  };
  const auto preloadTarget = [this](const WorldSnapshot & snapshot) {
    const auto position = snapshot.joint_positions.find(profile_.gripper_joint);
    const double measured_contact_q6 =
      position != snapshot.joint_positions.end() && std::isfinite(position->second)
        ? position->second
        : profile_.q6_contact;
    return std::max(profile_.q6_safe_lower,
                    measured_contact_q6 - profile_.q6_regrasp_squeeze_offset);
  };
  if (!observer_ || !evidence_) {
    return {ActionStatus::FAILED,
            Failure{FailureCategory::CONFIGURATION,
                    "PHYSICAL_GRASP_EVIDENCE_DEPENDENCY_MISSING",
                    "Physical-grasp stability checks require the production world observer",
                    {}}};
  }
  std::optional<WorldSnapshot> last;
  const int required_consecutive = before_lift ? 6 : 3;
  const int max_samples_per_phase = before_lift ? 30 : 3;
  int consecutive = 0;
  int consecutive_unilateral = 0;
  int samples_in_phase = 0;
  bool regrasp_attempted = false;
  int normalization_adjustments = 0;
  double last_gripper_target =
    std::max(profile_.q6_safe_lower, profile_.q6_contact - profile_.q6_regrasp_squeeze_offset);
  while (samples_in_phase < max_samples_per_phase) {
    ++samples_in_phase;
    if (auto stopped = cancelled())
      return *stopped;
    const auto observed = observer_->observe();
    if (!observed.snapshot) {
      return {ActionStatus::FAILED, observed.failure.value_or(
                                      Failure{FailureCategory::OBSERVATION,
                                              "PHYSICAL_GRASP_STABILITY_OBSERVATION_FAILED",
                                              "Unable to collect physical-grasp stability evidence",
                                              {}})};
    }
    const auto & snapshot = *observed.snapshot;
    if (!snapshot.fresh || !snapshot.gazebo_task_object_stationary ||
        !snapshot.gazebo_task_object_pose_world) {
      return {ActionStatus::FAILED,
              Failure{FailureCategory::POSTCONDITION,
                      "PHYSICAL_GRASP_NOT_STABLE",
                      "Cup/contact/arm evidence was not stable for three samples",
                      {}}};
    }
    if (!snapshot.arm_stationary || !*snapshot.gazebo_task_object_stationary) {
      consecutive = 0;
      consecutive_unilateral = 0;
      if (samples_in_phase < max_samples_per_phase)
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
      continue;
    }
    const bool bilateral =
      snapshot.gazebo_task_object_gripper_contact.value_or(false) &&
      snapshot.gazebo_task_object_fixed_finger_contact.value_or(false) &&
      snapshot.gazebo_task_object_moving_jaw_contact.value_or(false) &&
      snapshot.gazebo_task_object_gripper_max_depth &&
      *snapshot.gazebo_task_object_gripper_max_depth <= profile_.max_gripper_contact_depth;
    if (!before_lift || bilateral) {
      if (before_lift && regrasp_attempted && snapshot.gazebo_task_object_gripper_max_depth) {
        const double depth = *snapshot.gazebo_task_object_gripper_max_depth;
        if (depth < kMinimumTargetPenetrationM || depth > kMaximumTargetPenetrationM) {
          if (normalization_adjustments >= kMaximumNormalizationAdjustments) {
            return {ActionStatus::FAILED,
                    Failure{FailureCategory::POSTCONDITION,
                            "PHYSICAL_GRASP_PENETRATION_NORMALIZATION_EXHAUSTED",
                            "Grasp penetration did not enter the target interval after four "
                            "bounded adjustments",
                            {{"actual_penetration_m", depth},
                             {"target_min_penetration_m", kMinimumTargetPenetrationM},
                             {"target_max_penetration_m", kMaximumTargetPenetrationM},
                             {"hard_max_penetration_m", profile_.max_gripper_contact_depth}}}};
          }
          if (!gripper_) {
            return {ActionStatus::FAILED,
                    Failure{FailureCategory::CONFIGURATION,
                            "PHYSICAL_REGRASP_COMMAND_MISSING",
                            "Penetration normalization requires the production gripper command",
                            {}}};
          }
          const auto position = snapshot.joint_positions.find(profile_.gripper_joint);
          const double current =
            position != snapshot.joint_positions.end() ? position->second : last_gripper_target;
          const double requested = depth > kMaximumTargetPenetrationM
                                     ? current + kNormalizationStepQ6
                                     : current - kNormalizationStepQ6;
          const double target =
            std::clamp(requested, profile_.q6_safe_lower, profile_.q6_full_open);
          if (auto stopped = cancelled())
            return *stopped;
          const auto adjusted = gripper_->command(target);
          const bool contact_abort = adjusted.status == ActionStatus::FAILED && adjusted.failure &&
                                     adjusted.failure->code == "GRIPPER_ACTION_ABORTED";
          if (adjusted.status != ActionStatus::SUCCEEDED && !contact_abort)
            return adjusted;
          ++normalization_adjustments;
          last_gripper_target = target;
          consecutive = 0;
          last.reset();
          samples_in_phase = 0;
          continue;
        }
      }
      ++consecutive;
      consecutive_unilateral = 0;
      last = snapshot;
      if (consecutive >= required_consecutive) {
        if (before_lift && !regrasp_attempted) {
          if (auto stopped = cancelled())
            return *stopped;
          if (!gripper_) {
            return {ActionStatus::FAILED,
                    Failure{FailureCategory::CONFIGURATION,
                            "PHYSICAL_REGRASP_COMMAND_MISSING",
                            "Bilateral contact retry requires the production gripper command",
                            {}}};
          }
          const double retry_target = preloadTarget(snapshot);
          const auto retry = gripper_->command(retry_target);
          const bool contact_abort = retry.status == ActionStatus::FAILED && retry.failure &&
                                     retry.failure->code == "GRIPPER_ACTION_ABORTED";
          if (retry.status != ActionStatus::SUCCEEDED && !contact_abort)
            return retry;
          regrasp_attempted = true;
          last_gripper_target = retry_target;
          consecutive = 0;
          last.reset();
          samples_in_phase = 0;
        } else {
          break;
        }
      }
    } else {
      consecutive = 0;
      ++consecutive_unilateral;
      if (!regrasp_attempted && consecutive_unilateral >= 1) {
        if (!gripper_) {
          return {ActionStatus::FAILED,
                  Failure{FailureCategory::CONFIGURATION,
                          "PHYSICAL_REGRASP_COMMAND_MISSING",
                          "Bilateral contact retry requires the production gripper command",
                          {}}};
        }
        const double retry_target = preloadTarget(snapshot);
        if (auto stopped = cancelled())
          return *stopped;
        const auto retry = gripper_->command(retry_target);
        const bool contact_abort = retry.status == ActionStatus::FAILED && retry.failure &&
                                   retry.failure->code == "GRIPPER_ACTION_ABORTED";
        if (retry.status != ActionStatus::SUCCEEDED && !contact_abort)
          return retry;
        regrasp_attempted = true;
        last_gripper_target = retry_target;
        samples_in_phase = 0;
      }
    }
    if (samples_in_phase < max_samples_per_phase)
      std::this_thread::sleep_for(std::chrono::milliseconds(50));
  }
  if (!last || consecutive < required_consecutive) {
    return {ActionStatus::FAILED, Failure{FailureCategory::POSTCONDITION,
                                          "PHYSICAL_GRASP_BILATERAL_STABILITY_TIMEOUT",
                                          "Bilateral fixed-finger and moving-jaw contact did not "
                                          "remain stable after one bounded regrasp",
                                          {}}};
  }
  if (auto stopped = cancelled())
    return *stopped;
  const auto failure = before_lift ? evidence_->saveBefore(*last) : evidence_->saveAfter(*last);
  if (failure)
    return {ActionStatus::FAILED, *failure};
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

}  // namespace so101_gazebo_demo::pick_place
