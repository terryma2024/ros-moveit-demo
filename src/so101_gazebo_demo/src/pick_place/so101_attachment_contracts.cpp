#include "so101_gazebo_demo/pick_place/so101_attachment_contracts.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <set>
#include <utility>

#include "so101_gazebo_demo/pick_place/so101_gripper_validation.hpp"
#include "so101_gazebo_demo/pick_place/so101_gripper_state.hpp"

namespace so101_gazebo_demo::pick_place
{
namespace
{

using Contract = TransitionContractRegistry::ITransitionContract;

bool sameKey(TransitionKey first, TransitionKey second)
{
  return first.from == second.from && first.to == second.to;
}

bool isRecovery(TransitionKey key)
{
  return key.from == State::RECOVER_DETACH_GAZEBO ||
         key.from == State::RECOVER_DETACH_MOVEIT ||
         key.from == State::RECOVER_SYNC_WORLD_OBJECT;
}

double positionDistance(const Pose3d & first, const Pose3d & second)
{
  return std::hypot(std::hypot(first.x - second.x, first.y - second.y), first.z - second.z);
}

double orientationDistance(const Pose3d & first, const Pose3d & second)
{
  const double first_norm =
    std::hypot(std::hypot(first.qx, first.qy), std::hypot(first.qz, first.qw));
  const double second_norm =
    std::hypot(std::hypot(second.qx, second.qy), std::hypot(second.qz, second.qw));
  if (!std::isfinite(first_norm) || !std::isfinite(second_norm) || first_norm <= 1e-12 ||
      second_norm <= 1e-12) {
    return INFINITY;
  }
  const double dot = std::abs((first.qx * second.qx + first.qy * second.qy +
                               first.qz * second.qz + first.qw * second.qw) /
                              (first_norm * second_norm));
  return 2.0 * std::acos(std::clamp(dot, 0.0, 1.0));
}

void add(ValidationResult & result, FailureCategory category, std::string code,
         std::string message)
{
  result.failures.push_back({category, std::move(code), std::move(message), {}});
}

void merge(ValidationResult & result, ValidationResult additional)
{
  result.metrics.insert(additional.metrics.begin(), additional.metrics.end());
  result.failures.insert(result.failures.end(), additional.failures.begin(),
                         additional.failures.end());
}

void requireObserved(ValidationResult & result, const WorldSnapshot & snapshot)
{
  if (!snapshot.fresh) {
    add(result, FailureCategory::OBSERVATION, "STALE_WORLD_SNAPSHOT",
        "Attachment transitions require a fresh world observation");
  }
  if (!snapshot.arm_stationary) {
    add(result, FailureCategory::PRECONDITION, "ARM_NOT_QUIESCENT",
        "The arm must be stationary at attachment boundaries");
  }
  if (!snapshot.gazebo_coke_attached || !snapshot.moveit_coke_attached) {
    add(result, FailureCategory::WORLD_INCONSISTENCY, "ATTACHMENT_STATE_UNKNOWN",
        "Both Gazebo and MoveIt attachment facts are required");
  }
  if (!snapshot.gazebo_coke_pose_world) {
    add(result, FailureCategory::OBSERVATION, "GAZEBO_COKE_POSE_UNAVAILABLE",
        "Gazebo Coke pose is required at attachment boundaries");
  }
  if (!snapshot.gazebo_coke_stationary || !*snapshot.gazebo_coke_stationary) {
    add(result, FailureCategory::POSTCONDITION, "COKE_NOT_STATIONARY",
        "Gazebo Coke must be stationary at attachment boundaries");
  }
}

void requireAttachments(ValidationResult & result, const WorldSnapshot & snapshot,
                        bool gazebo, bool moveit)
{
  if (!snapshot.gazebo_coke_attached || *snapshot.gazebo_coke_attached != gazebo) {
    add(result, FailureCategory::GAZEBO_ATTACHMENT, "GAZEBO_ATTACHMENT_MISMATCH",
        "Gazebo attachment state does not match the transition boundary");
  }
  if (!snapshot.moveit_coke_attached || *snapshot.moveit_coke_attached != moveit) {
    add(result, FailureCategory::MOVEIT_SCENE, "MOVEIT_ATTACHMENT_MISMATCH",
        "MoveIt attachment state does not match the transition boundary");
  }
}

void requireQ6(ValidationResult & result, const WorldSnapshot & snapshot, bool open,
               const SO101Profile & profile)
{
  merge(result, validateSO101GripperTarget(
                  snapshot,
                  open ? SO101GripperTarget::PREOPEN : SO101GripperTarget::CONTACT,
                  profile));
}

void requireNoCokeJump(ValidationResult & result, const WorldSnapshot & before,
                       const WorldSnapshot & after, const SO101Profile & profile)
{
  if (!before.gazebo_coke_pose_world || !after.gazebo_coke_pose_world) {
    add(result, FailureCategory::OBSERVATION, "GAZEBO_COKE_POSE_UNAVAILABLE",
        "Gazebo Coke poses are required before and after attachment");
    return;
  }
  const double position =
    positionDistance(*before.gazebo_coke_pose_world, *after.gazebo_coke_pose_world);
  const double orientation =
    orientationDistance(*before.gazebo_coke_pose_world, *after.gazebo_coke_pose_world);
  result.metrics["coke_position_drift"] = position;
  result.metrics["coke_orientation_drift_rad"] = orientation;
  if (!std::isfinite(position) || position > profile.coke_position_drift_tolerance) {
    add(result, FailureCategory::POSTCONDITION, "COKE_POSITION_DRIFT",
        "Attachment moved Coke beyond the configured position tolerance");
  }
  if (!std::isfinite(orientation) ||
      orientation > profile.coke_orientation_drift_tolerance_rad) {
    add(result, FailureCategory::POSTCONDITION, "COKE_ORIENTATION_DRIFT",
        "Attachment rotated Coke beyond the configured orientation tolerance");
  }
}

bool requiresStableSupport(TransitionKey key)
{
  return key.from == State::DETACH_GAZEBO || key.from == State::DETACH_MOVEIT ||
         key.from == State::SYNC_WORLD_OBJECT || isRecovery(key);
}

void requireExpectedSupportPose(ValidationResult & result, const WorldSnapshot & before,
                                const WorldSnapshot & after, TransitionKey key,
                                const SO101Profile & profile)
{
  if (!before.gazebo_coke_pose_world || !after.gazebo_coke_pose_world) return;
  const auto & expected = isRecovery(key) ? profile.coke_pose : profile.place_coke_pose;
  const double before_position = positionDistance(*before.gazebo_coke_pose_world, expected);
  const double before_orientation = orientationDistance(*before.gazebo_coke_pose_world, expected);
  const double after_position = positionDistance(*after.gazebo_coke_pose_world, expected);
  const double after_orientation = orientationDistance(*after.gazebo_coke_pose_world, expected);
  result.metrics["coke_support_before_position_error"] = before_position;
  result.metrics["coke_support_before_orientation_error_rad"] = before_orientation;
  result.metrics["coke_support_after_position_error"] = after_position;
  result.metrics["coke_support_after_orientation_error_rad"] = after_orientation;
  if (!std::isfinite(before_position) || !std::isfinite(before_orientation) ||
      !std::isfinite(after_position) || !std::isfinite(after_orientation) ||
      before_position > profile.coke_position_drift_tolerance ||
      before_orientation > profile.coke_orientation_drift_tolerance_rad ||
      after_position > profile.coke_position_drift_tolerance ||
      after_orientation > profile.coke_orientation_drift_tolerance_rad) {
    add(result, FailureCategory::WORLD_INCONSISTENCY, "COKE_SUPPORT_POSE_MISMATCH",
        "Detach and sync transitions require Coke at the state-specific support pose");
  }
}

void requireExactMoveItAttachment(ValidationResult & result, const WorldSnapshot & snapshot,
                                  const SO101Profile & profile)
{
  const std::set<std::string> expected(profile.moveit_touch_links.begin(),
                                       profile.moveit_touch_links.end());
  if (!snapshot.moveit_coke_attached_link ||
      *snapshot.moveit_coke_attached_link != profile.moveit_attach_link) {
    add(result, FailureCategory::MOVEIT_SCENE, "MOVEIT_ATTACHED_LINK_MISMATCH",
        "MoveIt Coke attachment link does not match the SO-101 profile");
  }
  if (snapshot.moveit_coke_touch_links != expected) {
    add(result, FailureCategory::MOVEIT_SCENE, "MOVEIT_TOUCH_LINKS_MISMATCH",
        "MoveIt Coke touch links do not match the SO-101 profile");
  }
  if (!snapshot.moveit_coke_attached_relative_pose ||
      positionDistance(*snapshot.moveit_coke_attached_relative_pose,
                       profile.calibrated_grasp_relative_pose) >
        profile.coke_position_drift_tolerance ||
      orientationDistance(*snapshot.moveit_coke_attached_relative_pose,
                          profile.calibrated_grasp_relative_pose) >
        profile.coke_orientation_drift_tolerance_rad) {
    add(result, FailureCategory::MOVEIT_SCENE, "MOVEIT_ATTACHED_RELATIVE_POSE_MISMATCH",
        "MoveIt Coke attachment must preserve the calibrated full 6D relative pose");
  }
  if (snapshot.moveit_world_object_poses.count(profile.coke_model) != 0) {
    add(result, FailureCategory::MOVEIT_SCENE, "MOVEIT_ATTACHED_COKE_STILL_IN_WORLD",
        "Attached Coke must not remain in the MoveIt world");
  }
}

void requireDetachedMoveItWorld(ValidationResult & result, const WorldSnapshot & snapshot,
                                const SO101Profile & profile)
{
  if (snapshot.moveit_world_object_poses.count(profile.coke_model) != 1) {
    add(result, FailureCategory::MOVEIT_SCENE, "COKE_MISSING_FROM_MOVEIT_WORLD",
        "Detached Coke must exist in the MoveIt world");
  }
  if (snapshot.moveit_coke_attached_link || !snapshot.moveit_coke_touch_links.empty()) {
    add(result, FailureCategory::MOVEIT_SCENE, "MOVEIT_DETACH_METADATA_RETAINED",
        "Detached Coke must not retain attachment metadata");
  }
}

class AttachmentContract final : public Contract
{
public:
  AttachmentContract(TransitionKey key, SO101Profile profile) :
      key_(key), profile_(std::move(profile))
  {
  }

  ValidationResult validatePrecondition(const WorldSnapshot & before) const override
  {
    ValidationResult result{true, {}, {}};
    requireObserved(result, before);
    const bool open = key_.from == State::DETACH_GAZEBO ||
                      key_.from == State::DETACH_MOVEIT ||
                      key_.from == State::SYNC_WORLD_OBJECT || isRecovery(key_);
    requireQ6(result, before, open, profile_);
    if (requiresStableSupport(key_)) {
      requireExpectedSupportPose(result, before, before, key_, profile_);
    }
    if (key_.from == State::ATTACH_GAZEBO) {
      requireAttachments(result, before, false, false);
    } else if (key_.from == State::ATTACH_MOVEIT) {
      requireAttachments(result, before, true, false);
      requireDetachedMoveItWorld(result, before, profile_);
    } else if (key_.from == State::DETACH_GAZEBO) {
      requireAttachments(result, before, true, true);
    } else if (key_.from == State::DETACH_MOVEIT) {
      requireAttachments(result, before, false, true);
    } else if (key_.from == State::SYNC_WORLD_OBJECT) {
      requireAttachments(result, before, false, false);
      requireDetachedMoveItWorld(result, before, profile_);
    }
    result.ok = result.failures.empty();
    return result;
  }

  ValidationResult validate(const WorldSnapshot & before, const WorldSnapshot & after,
                            const ActionResult & action) const override
  {
    ValidationResult result{true, {}, {}};
    if (action.status != ActionStatus::SUCCEEDED) {
      add(result, FailureCategory::EXECUTION, "ACTION_DID_NOT_SUCCEED",
          "The attachment or scene action did not report success");
    }
    requireObserved(result, after);
    const bool open = key_.from == State::DETACH_GAZEBO ||
                      key_.from == State::DETACH_MOVEIT ||
                      key_.from == State::SYNC_WORLD_OBJECT || isRecovery(key_);
    requireQ6(result, after, open, profile_);
    if (requiresStableSupport(key_)) {
      requireNoCokeJump(result, before, after, profile_);
      requireExpectedSupportPose(result, before, after, key_, profile_);
    }
    if (key_.from == State::ATTACH_GAZEBO) {
      requireAttachments(result, after, true, false);
      requireNoCokeJump(result, before, after, profile_);
    } else if (key_.from == State::ATTACH_MOVEIT) {
      requireAttachments(result, after, true, true);
      requireExactMoveItAttachment(result, after, profile_);
      requireNoCokeJump(result, before, after, profile_);
    } else if (key_.from == State::DETACH_GAZEBO ||
               key_.from == State::RECOVER_DETACH_GAZEBO) {
      const bool moveit = key_.from == State::DETACH_GAZEBO
                            ? true
                            : after.moveit_coke_attached && *after.moveit_coke_attached;
      requireAttachments(result, after, false, moveit);
    } else if (key_.from == State::DETACH_MOVEIT ||
               key_.from == State::RECOVER_DETACH_MOVEIT) {
      requireAttachments(result, after, false, false);
      requireDetachedMoveItWorld(result, after, profile_);
    } else {
      requireAttachments(result, after, false, false);
      requireDetachedMoveItWorld(result, after, profile_);
      const auto moveit_coke = after.moveit_world_object_poses.find(profile_.coke_model);
      if (!after.gazebo_coke_pose_world || moveit_coke == after.moveit_world_object_poses.end()) {
        add(result, FailureCategory::OBSERVATION, "COKE_POSE_SYNC_EVIDENCE_MISSING",
            "Independent Gazebo and MoveIt Coke poses are required after sync");
      } else {
        const double position = positionDistance(*after.gazebo_coke_pose_world, moveit_coke->second);
        const double orientation =
          orientationDistance(*after.gazebo_coke_pose_world, moveit_coke->second);
        result.metrics["world_coke_position_error"] = position;
        result.metrics["world_coke_orientation_error_rad"] = orientation;
        if (position > profile_.coke_position_drift_tolerance ||
            orientation > profile_.coke_orientation_drift_tolerance_rad) {
          add(result, FailureCategory::WORLD_INCONSISTENCY, "COKE_WORLD_POSES_DIVERGED",
              "Independent Gazebo and MoveIt Coke 6D poses do not agree");
        }
      }
      const auto table = after.moveit_world_object_poses.find(profile_.table_object);
      if (table == after.moveit_world_object_poses.end() ||
          positionDistance(table->second, profile_.table_pose) > 1e-5 ||
          orientationDistance(table->second, profile_.table_pose) > 1e-4) {
        add(result, FailureCategory::MOVEIT_SCENE, "TABLE_WORLD_POSE_MISMATCH",
            "MoveIt table must remain at the canonical profile pose");
      }
    }
    result.ok = result.failures.empty();
    for (auto & failure_item : result.failures) {
      failure_item.metrics.insert(result.metrics.begin(), result.metrics.end());
    }
    return result;
  }

private:
  TransitionKey key_;
  SO101Profile profile_;
};

constexpr std::array<TransitionKey, 8> kAttachmentTransitions{{
  {State::ATTACH_GAZEBO, State::ATTACH_MOVEIT},
  {State::ATTACH_MOVEIT, State::LIFT},
  {State::DETACH_GAZEBO, State::DETACH_MOVEIT},
  {State::DETACH_MOVEIT, State::SYNC_WORLD_OBJECT},
  {State::SYNC_WORLD_OBJECT, State::RETREAT},
  {State::RECOVER_DETACH_GAZEBO, State::RECOVER_DETACH_MOVEIT},
  {State::RECOVER_DETACH_MOVEIT, State::RECOVER_SYNC_WORLD_OBJECT},
  {State::RECOVER_SYNC_WORLD_OBJECT, State::RECOVER_RETREAT},
}};

bool supported(TransitionKey key)
{
  return std::any_of(kAttachmentTransitions.begin(), kAttachmentTransitions.end(),
                     [key](TransitionKey candidate) { return sameKey(key, candidate); });
}

}  // namespace

std::shared_ptr<const Contract> makeSO101AttachmentContract(TransitionKey key,
                                                            SO101Profile profile)
{
  if (!supported(key)) {
    return {};
  }
  return std::make_shared<AttachmentContract>(key, std::move(profile));
}

void registerSO101AttachmentContracts(TransitionContractRegistry & registry,
                                      SO101Profile profile)
{
  for (const auto key : kAttachmentTransitions) {
    registry.registerContract(key, makeSO101AttachmentContract(key, profile));
  }
}

}  // namespace so101_gazebo_demo::pick_place
