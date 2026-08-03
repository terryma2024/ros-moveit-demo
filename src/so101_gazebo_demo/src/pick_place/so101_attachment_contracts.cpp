#include "so101_gazebo_demo/pick_place/so101_attachment_contracts.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
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
  return key.from == State::RECOVER_DETACH_GAZEBO || key.from == State::RECOVER_DETACH_MOVEIT ||
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
  const double dot = std::abs(
    (first.qx * second.qx + first.qy * second.qy + first.qz * second.qz + first.qw * second.qw) /
    (first_norm * second_norm));
  return 2.0 * std::acos(std::clamp(dot, 0.0, 1.0));
}

void add(ValidationResult & result, FailureCategory category, std::string code, std::string message)
{
  result.failures.push_back({category, std::move(code), std::move(message), {}});
}

void merge(ValidationResult & result, ValidationResult additional)
{
  result.metrics.insert(additional.metrics.begin(), additional.metrics.end());
  result.failures.insert(result.failures.end(), additional.failures.begin(),
                         additional.failures.end());
}

void requireObserved(ValidationResult & result, const WorldSnapshot & snapshot,
                     const SO101Profile & profile)
{
  if (!snapshot.fresh) {
    add(result, FailureCategory::OBSERVATION, "STALE_WORLD_SNAPSHOT",
        "Attachment transitions require a fresh world observation");
  }
  if (!snapshot.arm_stationary) {
    Failure failure{FailureCategory::PRECONDITION,
                    "ARM_NOT_QUIESCENT",
                    "The arm must be stationary at attachment boundaries",
                    {{"stationary_velocity_limit", profile.q6_velocity_tolerance},
                     {"q6_included_in_stationary_decision", 0.0}}};
    for (const auto & name : profile.arm_joints) {
      const auto velocity = snapshot.joint_velocities.find(name);
      if (velocity != snapshot.joint_velocities.end()) {
        failure.metrics["actual_velocity_" + name] = velocity->second;
      }
    }
    const auto q6_velocity = snapshot.joint_velocities.find(profile.gripper_joint);
    if (q6_velocity != snapshot.joint_velocities.end()) {
      failure.metrics["actual_velocity_" + profile.gripper_joint] = q6_velocity->second;
    }
    result.failures.push_back(std::move(failure));
  }
  if (!snapshot.gazebo_task_object_attached || !snapshot.moveit_task_object_attached) {
    add(result, FailureCategory::WORLD_INCONSISTENCY, "ATTACHMENT_STATE_UNKNOWN",
        "Both Gazebo and MoveIt attachment facts are required");
  }
  if (!snapshot.gazebo_task_object_pose_world) {
    add(result, FailureCategory::OBSERVATION, "GAZEBO_TASK_OBJECT_POSE_UNAVAILABLE",
        "Gazebo TaskObject pose is required at attachment boundaries");
  }
  if (!snapshot.gazebo_task_object_stationary || !*snapshot.gazebo_task_object_stationary) {
    add(result, FailureCategory::POSTCONDITION, "TASK_OBJECT_NOT_STATIONARY",
        "Gazebo TaskObject must be stationary at attachment boundaries");
  }
}

void requireAttachments(ValidationResult & result, const WorldSnapshot & snapshot, bool gazebo,
                        bool moveit)
{
  if (!snapshot.gazebo_task_object_attached || *snapshot.gazebo_task_object_attached != gazebo) {
    add(result, FailureCategory::GAZEBO_ATTACHMENT, "GAZEBO_ATTACHMENT_MISMATCH",
        "Gazebo attachment state does not match the transition boundary");
  }
  if (!snapshot.moveit_task_object_attached || *snapshot.moveit_task_object_attached != moveit) {
    add(result, FailureCategory::MOVEIT_SCENE, "MOVEIT_ATTACHMENT_MISMATCH",
        "MoveIt attachment state does not match the transition boundary");
  }
}

void requireQ6(ValidationResult & result, const WorldSnapshot & snapshot, SO101GripperTarget target,
               const SO101Profile & profile)
{
  merge(result, validateSO101GripperTarget(snapshot, target, profile));
}

void requireBilateralFingerContact(ValidationResult & result, const WorldSnapshot & snapshot,
                                   const SO101Profile & profile)
{
  const bool fixed = snapshot.gazebo_task_object_fixed_finger_contact.value_or(false);
  const bool moving = snapshot.gazebo_task_object_moving_jaw_contact.value_or(false);
  result.metrics["gazebo_task_object_fixed_finger_contact"] = fixed ? 1.0 : 0.0;
  result.metrics["gazebo_task_object_moving_jaw_contact"] = moving ? 1.0 : 0.0;
  if (!fixed || !moving) {
    add(result, FailureCategory::PRECONDITION, "BILATERAL_GRIPPER_CONTACT_REQUIRED",
        "Gazebo attach requires independent TaskObject contact on the fixed finger and moving jaw");
  }
  if (!snapshot.gazebo_task_object_gripper_max_depth ||
      !std::isfinite(*snapshot.gazebo_task_object_gripper_max_depth)) {
    add(result, FailureCategory::OBSERVATION, "CONTACT_PENETRATION_EVIDENCE_REQUIRED",
        "Gazebo attach requires a finite maximum TaskObject-finger penetration depth");
  } else {
    result.metrics["gazebo_task_object_gripper_solver_reported_max_depth"] =
      *snapshot.gazebo_task_object_gripper_max_depth;
    result.metrics["stable_solver_reported_depth_limit"] = profile.max_gripper_contact_depth;
    if (*snapshot.gazebo_task_object_gripper_max_depth < 0.0 ||
        *snapshot.gazebo_task_object_gripper_max_depth > profile.max_gripper_contact_depth) {
      add(result, FailureCategory::COLLISION, "GRIPPER_CONTACT_PENETRATION_EXCEEDED",
          "Stable-window Bullet solver-reported depth exceeds the conservative attach limit");
    }
  }
  const auto q6 = snapshot.joint_positions.find(profile.gripper_joint);
  if (q6 != snapshot.joint_positions.end() && std::isfinite(q6->second)) {
    result.metrics["q6_controller_error"] = q6->second - profile.q6_contact;
  }
}

void requireSameWallSurfaceContact(ValidationResult & result, const WorldSnapshot & snapshot,
                                   const TaskObjectConfig & object,
                                   const GraspContactValidationConfig & policy)
{
  const auto finite_vector = [](const ContactVector3 & value) {
    return std::isfinite(value.x) && std::isfinite(value.y) && std::isfinite(value.z);
  };
  const auto norm = [](const ContactVector3 & value) {
    return std::hypot(value.x, std::hypot(value.y, value.z));
  };
  const auto & outward = object.grasp_frame.near_wall_outward_world;
  const double outward_norm = std::hypot(outward.x, std::hypot(outward.y, outward.z));
  const auto & orientation = object.scene.spawn_pose;
  const double quaternion_norm = std::hypot(std::hypot(orientation.qx, orientation.qy),
                                            std::hypot(orientation.qz, orientation.qw));
  ContactVector3 outward_local{};
  if (quaternion_norm > 1e-12) {
    const double qx = -orientation.qx / quaternion_norm;
    const double qy = -orientation.qy / quaternion_norm;
    const double qz = -orientation.qz / quaternion_norm;
    const double qw = orientation.qw / quaternion_norm;
    const double tx = 2.0 * (qy * outward.z - qz * outward.y);
    const double ty = 2.0 * (qz * outward.x - qx * outward.z);
    const double tz = 2.0 * (qx * outward.y - qy * outward.x);
    outward_local = {outward.x + qw * tx + (qy * tz - qz * ty),
                     outward.y + qw * ty + (qz * tx - qx * tz),
                     outward.z + qw * tz + (qx * ty - qy * tx)};
  }
  const double outward_local_norm = norm(outward_local);
  if (!policy.require_fixed_finger || !policy.require_moving_jaw ||
      policy.required_wall_collision.empty() || policy.fixed_surface != "outside" ||
      policy.moving_surface != "inside" || outward_norm <= 1e-12 ||
      policy.max_penetration_m <= 0.0 || object.model.height_m <= 0.0 ||
      outward_local_norm <= 1e-12) {
    add(result, FailureCategory::CONFIGURATION, "GRASP_CONTACT_POLICY_INVALID",
        "Same-wall attachment contact policy is incomplete or inconsistent");
    return;
  }
  const std::set<std::string> forbidden(policy.forbidden_collisions.begin(),
                                        policy.forbidden_collisions.end());
  const auto validate_finger = [&](const std::vector<TaskObjectContactSample> & samples,
                                   bool outside, const char * finger) {
    if (samples.empty()) {
      add(result, FailureCategory::PRECONDITION, "SEMANTIC_FINGER_CONTACT_REQUIRED",
          std::string(finger) + " has no fresh cup contact samples");
      return;
    }
    for (const auto & sample : samples) {
      const double normal_norm = norm(sample.normal_toward_finger_world);
      const double alignment = normal_norm > 1e-12
                                 ? (sample.normal_toward_finger_world.x * outward.x +
                                    sample.normal_toward_finger_world.y * outward.y +
                                    sample.normal_toward_finger_world.z * outward.z) /
                                     (normal_norm * outward_norm)
                                 : 0.0;
      const double local_normal_norm = norm(sample.normal_toward_finger_task_object);
      const double local_alignment =
        local_normal_norm > 1e-12 ? (sample.normal_toward_finger_task_object.x * outward_local.x +
                                     sample.normal_toward_finger_task_object.y * outward_local.y +
                                     sample.normal_toward_finger_task_object.z * outward_local.z) /
                                      (local_normal_norm * outward_local_norm)
                                  : 0.0;
      const double below_rim = object.model.height_m / 2.0 - sample.point_task_object.z;
      const double bottom_clearance = sample.point_task_object.z + object.model.height_m / 2.0;
      if (forbidden.count(sample.task_object_collision) != 0U ||
          sample.task_object_collision != policy.required_wall_collision) {
        add(result, FailureCategory::COLLISION, "GRASP_CONTACT_WRONG_CUP_COLLISION",
            std::string(finger) + " must contact only the configured near wall");
      }
      if (!finite_vector(sample.point_world) || !finite_vector(sample.point_task_object) ||
          !finite_vector(sample.normal_toward_finger_world) || !std::isfinite(sample.depth) ||
          sample.depth < 0.0 || sample.depth > policy.max_penetration_m) {
        add(result, FailureCategory::COLLISION, "GRASP_CONTACT_SAMPLE_INVALID",
            std::string(finger) + " contact point, normal or depth violates policy");
      }
      if ((outside && (alignment <= 0.5 || local_alignment <= 0.5)) ||
          (!outside && (alignment >= -0.5 || local_alignment >= -0.5))) {
        add(result, FailureCategory::COLLISION, "GRASP_CONTACT_SURFACE_MISMATCH",
            std::string(finger) + " contact normal is on the wrong wall surface");
      }
      if (!std::isfinite(below_rim) || !std::isfinite(bottom_clearance) ||
          below_rim < policy.min_below_rim_m || below_rim > policy.max_below_rim_m ||
          bottom_clearance < policy.min_bottom_clearance_m) {
        add(result, FailureCategory::COLLISION, "GRASP_CONTACT_VERTICAL_BAND_MISMATCH",
            std::string(finger) + " contact is too close to the rim or cup bottom");
      }
    }
  };
  validate_finger(snapshot.gazebo_task_object_fixed_finger_contacts, true, "fixed finger");
  validate_finger(snapshot.gazebo_task_object_moving_jaw_contacts, false, "moving jaw");
}

void requireNoTaskObjectJump(ValidationResult & result, const WorldSnapshot & before,
                             const WorldSnapshot & after, const SO101Profile & profile)
{
  if (!before.gazebo_task_object_pose_world || !after.gazebo_task_object_pose_world) {
    add(result, FailureCategory::OBSERVATION, "GAZEBO_TASK_OBJECT_POSE_UNAVAILABLE",
        "Gazebo TaskObject poses are required before and after attachment");
    return;
  }
  const double position =
    positionDistance(*before.gazebo_task_object_pose_world, *after.gazebo_task_object_pose_world);
  const double orientation = orientationDistance(*before.gazebo_task_object_pose_world,
                                                 *after.gazebo_task_object_pose_world);
  result.metrics["task_object_position_drift"] = position;
  result.metrics["task_object_orientation_drift_rad"] = orientation;
  if (!std::isfinite(position) || position > profile.task_object_position_drift_tolerance) {
    add(result, FailureCategory::POSTCONDITION, "TASK_OBJECT_POSITION_DRIFT",
        "Attachment moved TaskObject beyond the configured position tolerance");
  }
  if (!std::isfinite(orientation) ||
      orientation > profile.task_object_orientation_drift_tolerance_rad) {
    add(result, FailureCategory::POSTCONDITION, "TASK_OBJECT_ORIENTATION_DRIFT",
        "Attachment rotated TaskObject beyond the configured orientation tolerance");
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
  if (!before.gazebo_task_object_pose_world || !after.gazebo_task_object_pose_world)
    return;
  const auto & expected =
    isRecovery(key) ? profile.task_object_pose : profile.place_task_object_pose;
  const double before_position = positionDistance(*before.gazebo_task_object_pose_world, expected);
  const double before_orientation =
    orientationDistance(*before.gazebo_task_object_pose_world, expected);
  const double after_position = positionDistance(*after.gazebo_task_object_pose_world, expected);
  const double after_orientation =
    orientationDistance(*after.gazebo_task_object_pose_world, expected);
  result.metrics["task_object_support_before_position_error"] = before_position;
  result.metrics["task_object_support_before_orientation_error_rad"] = before_orientation;
  result.metrics["task_object_support_after_position_error"] = after_position;
  result.metrics["task_object_support_after_orientation_error_rad"] = after_orientation;
  const auto place_supported = [&](const Pose3d & pose, const char * phase) {
    const double xy_error = std::hypot(pose.x - expected.x, pose.y - expected.y);
    const double height_error = std::abs(pose.z - expected.z);
    const double norm = std::hypot(std::hypot(pose.qx, pose.qy), std::hypot(pose.qz, pose.qw));
    const double local_z_world_z =
      norm > 1e-12 ? 1.0 - 2.0 * (pose.qx * pose.qx + pose.qy * pose.qy) / (norm * norm)
                   : std::numeric_limits<double>::quiet_NaN();
    const double tilt = std::acos(std::clamp(local_z_world_z, -1.0, 1.0));
    result.metrics[std::string("task_object_support_") + phase + "_xy_error"] = xy_error;
    result.metrics[std::string("task_object_support_") + phase + "_height_error"] = height_error;
    result.metrics[std::string("task_object_support_") + phase + "_tilt_error_rad"] = tilt;
    const bool detaching = key.from == State::DETACH_GAZEBO || key.from == State::DETACH_MOVEIT;
    const double xy_tolerance =
      detaching ? profile.place_detach_xy_tolerance : profile.place_support_xy_tolerance;
    return std::isfinite(xy_error) && std::isfinite(height_error) && std::isfinite(tilt) &&
           xy_error <= xy_tolerance && height_error <= profile.place_support_height_tolerance &&
           tilt <= profile.place_support_tilt_tolerance_rad;
  };
  const bool supported =
    isRecovery(key) ? std::isfinite(before_position) && std::isfinite(before_orientation) &&
                        std::isfinite(after_position) && std::isfinite(after_orientation) &&
                        before_position <= profile.task_object_position_drift_tolerance &&
                        before_orientation <= profile.task_object_orientation_drift_tolerance_rad &&
                        after_position <= profile.task_object_position_drift_tolerance &&
                        after_orientation <= profile.task_object_orientation_drift_tolerance_rad
                    : place_supported(*before.gazebo_task_object_pose_world, "before") &&
                        place_supported(*after.gazebo_task_object_pose_world, "after");
  if (!supported) {
    add(
      result, FailureCategory::WORLD_INCONSISTENCY, "TASK_OBJECT_SUPPORT_POSE_MISMATCH",
      "Detach and sync transitions require TaskObject inside the state-specific support envelope");
  }
}

void requireExactMoveItAttachment(ValidationResult & result, const WorldSnapshot & snapshot,
                                  const SO101Profile & profile)
{
  const std::set<std::string> expected(profile.moveit_touch_links.begin(),
                                       profile.moveit_touch_links.end());
  if (!snapshot.moveit_task_object_attached_link ||
      *snapshot.moveit_task_object_attached_link != profile.moveit_attach_link) {
    add(result, FailureCategory::MOVEIT_SCENE, "MOVEIT_ATTACHED_LINK_MISMATCH",
        "MoveIt TaskObject attachment link does not match the SO-101 profile");
  }
  if (snapshot.moveit_task_object_touch_links != expected) {
    add(result, FailureCategory::MOVEIT_SCENE, "MOVEIT_TOUCH_LINKS_MISMATCH",
        "MoveIt TaskObject touch links do not match the SO-101 profile");
  }
  if (!snapshot.moveit_task_object_attached_relative_pose ||
      positionDistance(*snapshot.moveit_task_object_attached_relative_pose,
                       profile.calibrated_grasp_relative_pose) >
        profile.task_object_position_drift_tolerance ||
      orientationDistance(*snapshot.moveit_task_object_attached_relative_pose,
                          profile.calibrated_grasp_relative_pose) >
        profile.task_object_orientation_drift_tolerance_rad) {
    add(result, FailureCategory::MOVEIT_SCENE, "MOVEIT_ATTACHED_RELATIVE_POSE_MISMATCH",
        "MoveIt TaskObject attachment must preserve the calibrated full 6D relative pose");
  }
  if (snapshot.moveit_world_object_poses.count(profile.task_object_id) != 0) {
    add(result, FailureCategory::MOVEIT_SCENE, "MOVEIT_ATTACHED_TASK_OBJECT_STILL_IN_WORLD",
        "Attached TaskObject must not remain in the MoveIt world");
  }
}

void requireDetachedMoveItWorld(ValidationResult & result, const WorldSnapshot & snapshot,
                                const SO101Profile & profile)
{
  if (snapshot.moveit_world_object_poses.count(profile.task_object_id) != 1) {
    add(result, FailureCategory::MOVEIT_SCENE, "TASK_OBJECT_MISSING_FROM_MOVEIT_WORLD",
        "Detached TaskObject must exist in the MoveIt world");
  }
  if (snapshot.moveit_task_object_attached_link ||
      !snapshot.moveit_task_object_touch_links.empty()) {
    add(result, FailureCategory::MOVEIT_SCENE, "MOVEIT_DETACH_METADATA_RETAINED",
        "Detached TaskObject must not retain attachment metadata");
  }
}

class AttachmentContract final : public Contract
{
public:
  AttachmentContract(TransitionKey key, SO101Profile profile, TaskObjectConfig object,
                     GraspContactValidationConfig grasp_contact) :
      key_(key), profile_(std::move(profile)), object_(std::move(object)),
      grasp_contact_(std::move(grasp_contact))
  {
  }

  [[nodiscard]] ValidationResult validatePrecondition(const WorldSnapshot & before) const override
  {
    ValidationResult result{true, {}, {}};
    requireObserved(result, before, profile_);
    const auto gripper_target = key_.from == State::DETACH_GAZEBO ||
                                    key_.from == State::DETACH_MOVEIT ||
                                    key_.from == State::SYNC_WORLD_OBJECT || isRecovery(key_)
                                  ? SO101GripperTarget::FULL_OPEN
                                  : SO101GripperTarget::CONTACT;
    requireQ6(result, before, gripper_target, profile_);
    if (requiresStableSupport(key_)) {
      requireExpectedSupportPose(result, before, before, key_, profile_);
    }
    if (key_.from == State::ATTACH_GAZEBO) {
      requireBilateralFingerContact(result, before, profile_);
      requireSameWallSurfaceContact(result, before, object_, grasp_contact_);
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

  [[nodiscard]] ValidationResult validate(const WorldSnapshot & before, const WorldSnapshot & after,
                                          const ActionResult & action) const override
  {
    ValidationResult result{true, {}, {}};
    if (action.status != ActionStatus::SUCCEEDED) {
      add(result, FailureCategory::EXECUTION, "ACTION_DID_NOT_SUCCEED",
          "The attachment or scene action did not report success");
    }
    requireObserved(result, after, profile_);
    const auto gripper_target = key_.from == State::DETACH_GAZEBO ||
                                    key_.from == State::DETACH_MOVEIT ||
                                    key_.from == State::SYNC_WORLD_OBJECT || isRecovery(key_)
                                  ? SO101GripperTarget::FULL_OPEN
                                  : SO101GripperTarget::CONTACT;
    requireQ6(result, after, gripper_target, profile_);
    if (requiresStableSupport(key_)) {
      // Removing the physical attachment intentionally lets the cup settle
      // onto the table.  Bound both endpoints by the place support envelope;
      // retain the no-jump invariant for recovery and post-release scene sync.
      if (isRecovery(key_) || key_.from == State::SYNC_WORLD_OBJECT) {
        requireNoTaskObjectJump(result, before, after, profile_);
      }
      requireExpectedSupportPose(result, before, after, key_, profile_);
    }
    if (key_.from == State::ATTACH_GAZEBO) {
      requireAttachments(result, after, true, false);
      requireNoTaskObjectJump(result, before, after, profile_);
    } else if (key_.from == State::ATTACH_MOVEIT) {
      requireAttachments(result, after, true, true);
      requireExactMoveItAttachment(result, after, profile_);
      requireNoTaskObjectJump(result, before, after, profile_);
    } else if (key_.from == State::DETACH_GAZEBO || key_.from == State::RECOVER_DETACH_GAZEBO) {
      const bool moveit = key_.from == State::DETACH_GAZEBO ? true
                                                            : after.moveit_task_object_attached &&
                                                                *after.moveit_task_object_attached;
      requireAttachments(result, after, false, moveit);
    } else if (key_.from == State::DETACH_MOVEIT || key_.from == State::RECOVER_DETACH_MOVEIT) {
      requireAttachments(result, after, false, false);
      requireDetachedMoveItWorld(result, after, profile_);
    } else {
      requireAttachments(result, after, false, false);
      requireDetachedMoveItWorld(result, after, profile_);
      const auto moveit_task_object = after.moveit_world_object_poses.find(profile_.task_object_id);
      if (!after.gazebo_task_object_pose_world ||
          moveit_task_object == after.moveit_world_object_poses.end()) {
        add(result, FailureCategory::OBSERVATION, "TASK_OBJECT_POSE_SYNC_EVIDENCE_MISSING",
            "Independent Gazebo and MoveIt TaskObject poses are required after sync");
      } else {
        const double position =
          positionDistance(*after.gazebo_task_object_pose_world, moveit_task_object->second);
        const double orientation =
          orientationDistance(*after.gazebo_task_object_pose_world, moveit_task_object->second);
        result.metrics["world_task_object_position_error"] = position;
        result.metrics["world_task_object_orientation_error_rad"] = orientation;
        if (position > profile_.task_object_position_drift_tolerance ||
            orientation > profile_.task_object_orientation_drift_tolerance_rad) {
          add(result, FailureCategory::WORLD_INCONSISTENCY, "TASK_OBJECT_WORLD_POSES_DIVERGED",
              "Independent Gazebo and MoveIt TaskObject 6D poses do not agree");
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
  TaskObjectConfig object_;
  GraspContactValidationConfig grasp_contact_;
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

std::shared_ptr<const Contract>
makeSO101AttachmentContract(TransitionKey key, const SO101Profile & profile,
                            const TaskObjectConfig & object,
                            const GraspContactValidationConfig & grasp_contact)
{
  if (!supported(key)) {
    return {};
  }
  return std::make_shared<AttachmentContract>(key, profile, object, grasp_contact);
}

void registerSO101AttachmentContracts(TransitionContractRegistry & registry,
                                      const SO101Profile & profile, const TaskObjectConfig & object,
                                      const GraspContactValidationConfig & grasp_contact)
{
  for (const auto key : kAttachmentTransitions) {
    registry.registerContract(key,
                              makeSO101AttachmentContract(key, profile, object, grasp_contact));
  }
}

}  // namespace so101_gazebo_demo::pick_place
