#include "panda_gazebo_demo/pick_place/recovery_contracts.hpp"

#include <cmath>
#include <functional>
#include <memory>
#include <set>
#include <string>
#include <utility>

namespace panda_gazebo_demo::pick_place
{
namespace
{

const std::set<std::string> kRequiredTouchLinks{"panda_hand", "panda_leftfinger",
                                                "panda_rightfinger"};

using ValidationFunction = std::function<ValidationResult(const WorldSnapshot &)>;
using PostValidationFunction = std::function<ValidationResult(
  const WorldSnapshot &, const WorldSnapshot &, const ActionResult &)>;

class FunctionalContract final : public Contract
{
public:
  FunctionalContract(ValidationFunction precondition, PostValidationFunction postcondition) :
      precondition_(std::move(precondition)), postcondition_(std::move(postcondition))
  {
  }

  [[nodiscard]] ValidationResult validatePrecondition(const WorldSnapshot & before) const override
  {
    return precondition_(before);
  }

  [[nodiscard]] ValidationResult validate(const WorldSnapshot & before, const WorldSnapshot & after,
                                          const ActionResult & action_result) const override
  {
    return postcondition_(before, after, action_result);
  }

private:
  ValidationFunction precondition_;
  PostValidationFunction postcondition_;
};

void addFailure(ValidationResult & result, FailureCategory category, std::string code,
                std::string message)
{
  result.failures.push_back({category, std::move(code), std::move(message), {}});
}

void merge(ValidationResult & result, ValidationResult additional)
{
  result.metrics.insert(additional.metrics.begin(), additional.metrics.end());
  result.failures.insert(result.failures.end(),
                         std::make_move_iterator(additional.failures.begin()),
                         std::make_move_iterator(additional.failures.end()));
}

ValidationResult finish(ValidationResult result)
{
  result.ok = result.failures.empty();
  for (auto & failure : result.failures) {
    failure.metrics.insert(result.metrics.begin(), result.metrics.end());
  }
  return result;
}

ValidationResult boundary(const WorldSnapshot & snapshot)
{
  ValidationResult result{true, {}, {}};
  result.metrics["snapshot_fresh"] = snapshot.fresh ? 1.0 : 0.0;
  result.metrics["arm_stationary"] = snapshot.arm_stationary ? 1.0 : 0.0;
  result.metrics["gazebo_attached"] =
    snapshot.gazebo_coke_attached ? (*snapshot.gazebo_coke_attached ? 1.0 : 0.0) : -1.0;
  result.metrics["moveit_attached"] =
    snapshot.moveit_coke_attached ? (*snapshot.moveit_coke_attached ? 1.0 : 0.0) : -1.0;
  result.metrics["coke_stationary"] =
    snapshot.gazebo_coke_stationary ? (*snapshot.gazebo_coke_stationary ? 1.0 : 0.0) : -1.0;
  if (!snapshot.fresh) {
    addFailure(result, FailureCategory::OBSERVATION, "STALE_WORLD_SNAPSHOT",
               "Recovery requires a fresh world observation");
  }
  if (!snapshot.arm_stationary) {
    addFailure(result, FailureCategory::PRECONDITION, "ARM_NOT_QUIESCENT",
               "Recovery requires a stationary arm at every boundary");
  }
  if (!snapshot.gazebo_coke_attached || !snapshot.moveit_coke_attached) {
    addFailure(result, FailureCategory::WORLD_INCONSISTENCY, "ATTACHMENT_STATE_UNKNOWN",
               "Recovery requires current Gazebo and MoveIt attachment facts");
  }
  if (!snapshot.gazebo_coke_pose_world) {
    addFailure(result, FailureCategory::OBSERVATION, "GAZEBO_COKE_POSE_UNAVAILABLE",
               "Recovery requires the current Gazebo Coke pose");
  }
  if (!snapshot.gazebo_coke_stationary || !*snapshot.gazebo_coke_stationary) {
    addFailure(result, FailureCategory::PRECONDITION, "COKE_NOT_STATIONARY",
               "Recovery requires a stationary Gazebo Coke");
  }
  return result;
}

void requireActionSucceeded(ValidationResult & result, const ActionResult & action_result)
{
  result.metrics["action_succeeded"] = action_result.status == ActionStatus::SUCCEEDED ? 1.0 : 0.0;
  if (action_result.status != ActionStatus::SUCCEEDED) {
    addFailure(result, FailureCategory::EXECUTION, "ACTION_DID_NOT_SUCCEED",
               "Recovery action did not report success");
  }
}

void requireAttachmentCombination(ValidationResult & result, const WorldSnapshot & snapshot,
                                  bool gazebo_attached, bool moveit_attached)
{
  merge(result, validateAttachmentState(snapshot, gazebo_attached, moveit_attached));
}

void requireBothAttached(ValidationResult & result, const WorldSnapshot & snapshot)
{
  requireAttachmentCombination(result, snapshot, true, true);
  const bool exact_link =
    snapshot.moveit_coke_attached_link && *snapshot.moveit_coke_attached_link == "panda_hand";
  result.metrics["moveit_attached_link_exact"] = exact_link ? 1.0 : 0.0;
  result.metrics["moveit_touch_links_exact"] =
    snapshot.moveit_coke_touch_links == kRequiredTouchLinks ? 1.0 : 0.0;
  if (!exact_link || snapshot.moveit_coke_touch_links != kRequiredTouchLinks ||
      snapshot.moveit_world_object_poses.count("coke") != 0) {
    addFailure(result, FailureCategory::MOVEIT_SCENE, "RECOVERY_ATTACHED_METADATA_INVALID",
               "Carrying recovery requires Coke attached to panda_hand with exact touch links");
  }
}

void requireGrasp(ValidationResult & result, const WorldSnapshot & snapshot,
                  const PickPlaceContractConfig & config)
{
  merge(result, validateGripperGrasp(snapshot, config.gripper));
}

void requireOpen(ValidationResult & result, const WorldSnapshot & snapshot,
                 const PickPlaceContractConfig & config)
{
  merge(result, validateGripperOpen(snapshot, config.gripper));
}

void requireReadyAndClosed(ValidationResult & result, const WorldSnapshot & snapshot,
                           const PickPlaceContractConfig & config)
{
  merge(result, validateNamedJointTarget(snapshot, config.ready_joint_positions,
                                         config.ready_joint_tolerance));
  merge(result, validateGripperClosed(snapshot, config.gripper_close_position,
                                      config.gripper_close_tolerance, config.gripper));
}

void requireWorldObjects(ValidationResult & result, const WorldSnapshot & snapshot)
{
  result.metrics["table_in_moveit_world"] =
    snapshot.moveit_world_object_poses.count("table") == 1 ? 1.0 : 0.0;
  result.metrics["coke_in_moveit_world"] =
    snapshot.moveit_world_object_poses.count("coke") == 1 ? 1.0 : 0.0;
  if (snapshot.moveit_world_object_poses.count("table") == 0 ||
      snapshot.moveit_world_object_poses.count("coke") == 0) {
    addFailure(result, FailureCategory::MOVEIT_SCENE, "RECOVERY_WORLD_OBJECTS_INCOMPLETE",
               "Detached recovery requires table and Coke in the MoveIt world");
  }
}

void requireTarget(ValidationResult & result, const WorldSnapshot & snapshot,
                   const TargetPolicyPtr & target_policy, State state, State next_state,
                   const PickPlaceContractConfig & config)
{
  if (!target_policy) {
    addFailure(result, FailureCategory::CONFIGURATION, "TARGET_POLICY_MISSING",
               "Recovery motion contract requires a target policy");
    return;
  }
  const auto target =
    target_policy->targetPose(state, next_state, ObservationResult{snapshot, std::nullopt});
  if (!target.target_pose) {
    result.failures.push_back(
      target.failure.value_or(Failure{FailureCategory::CONFIGURATION,
                                      "TARGET_POLICY_FAILED",
                                      "Recovery target policy did not return a target",
                                      {}}));
    return;
  }
  const double position_error = positionDistance(snapshot.tcp_pose_world, *target.target_pose);
  const double orientation_error =
    orientationDistance(snapshot.tcp_pose_world, *target.target_pose);
  result.metrics["tcp_position_error"] = position_error;
  result.metrics["tcp_orientation_error_rad"] = orientation_error;
  if (position_error > config.tcp_position_tolerance) {
    addFailure(result, FailureCategory::POSTCONDITION, "TCP_POSITION_OUTSIDE_TOLERANCE",
               "Recovery TCP position is outside the configured target tolerance");
  }
  if (orientation_error > config.tcp_orientation_tolerance_rad) {
    addFailure(result, FailureCategory::POSTCONDITION, "TCP_ORIENTATION_OUTSIDE_TOLERANCE",
               "Recovery TCP orientation is outside the configured target tolerance");
  }
}

void requireSupportedCoke(ValidationResult & result, const WorldSnapshot & snapshot,
                          const TargetPolicyPtr & target_policy, State state, State next_state,
                          const PickPlaceContractConfig & config)
{
  if (!snapshot.gazebo_coke_pose_world || !target_policy) {
    addFailure(result, FailureCategory::OBSERVATION, "RECOVERY_SUPPORTED_COKE_POSE_UNAVAILABLE",
               "Recovery support validation requires Coke observation and target policy");
    return;
  }
  const auto expected =
    supportedCokePose(*target_policy, state, next_state, ObservationResult{snapshot, std::nullopt});
  if (!expected.target_pose) {
    result.failures.push_back(expected.failure.value_or(
      Failure{FailureCategory::CONFIGURATION,
              "RECOVERY_SUPPORTED_COKE_TARGET_MISSING",
              "Recovery target policy did not return a supported Coke pose",
              {}}));
    return;
  }
  const double position_error =
    positionDistance(*snapshot.gazebo_coke_pose_world, *expected.target_pose);
  const double orientation_error =
    orientationDistance(*snapshot.gazebo_coke_pose_world, *expected.target_pose);
  result.metrics["supported_coke_position_error"] = position_error;
  result.metrics["supported_coke_orientation_error_rad"] = orientation_error;
  if (position_error > config.coke_position_tolerance ||
      orientation_error > config.coke_orientation_tolerance_rad) {
    addFailure(result, FailureCategory::POSTCONDITION, "RECOVERY_COKE_NOT_AT_SUPPORTED_POSE",
               "Recovery Coke is outside the derived support pose or upright orientation");
  }
}

void requireCokeDrift(ValidationResult & result, const WorldSnapshot & before,
                      const WorldSnapshot & after, const PickPlaceContractConfig & config)
{
  if (!before.gazebo_coke_pose_world || !after.gazebo_coke_pose_world) {
    addFailure(result, FailureCategory::OBSERVATION, "GAZEBO_COKE_POSE_UNAVAILABLE",
               "Recovery boundary requires Gazebo Coke poses before and after the action");
    return;
  }
  const double position_error =
    positionDistance(*before.gazebo_coke_pose_world, *after.gazebo_coke_pose_world);
  const double orientation_error =
    orientationDistance(*before.gazebo_coke_pose_world, *after.gazebo_coke_pose_world);
  result.metrics["coke_position_drift"] = position_error;
  result.metrics["coke_orientation_drift_rad"] = orientation_error;
  if (position_error > config.coke_position_tolerance) {
    addFailure(result, FailureCategory::POSTCONDITION, "COKE_POSITION_DRIFT",
               "Coke position changed beyond the recovery tolerance");
  }
  if (orientation_error > config.coke_orientation_tolerance_rad) {
    addFailure(result, FailureCategory::POSTCONDITION, "COKE_ORIENTATION_DRIFT",
               "Coke orientation changed beyond the recovery tolerance");
  }
}

struct Quaternion
{
  double x;
  double y;
  double z;
  double w;
};

Quaternion normalized(Quaternion value)
{
  const double norm =
    std::sqrt(value.x * value.x + value.y * value.y + value.z * value.z + value.w * value.w);
  if (!std::isfinite(norm) || norm <= 1.0e-12) {
    return {0.0, 0.0, 0.0, 1.0};
  }
  return {value.x / norm, value.y / norm, value.z / norm, value.w / norm};
}

Quaternion multiply(const Quaternion & lhs, const Quaternion & rhs)
{
  return {lhs.w * rhs.x + lhs.x * rhs.w + lhs.y * rhs.z - lhs.z * rhs.y,
          lhs.w * rhs.y - lhs.x * rhs.z + lhs.y * rhs.w + lhs.z * rhs.x,
          lhs.w * rhs.z + lhs.x * rhs.y - lhs.y * rhs.x + lhs.z * rhs.w,
          lhs.w * rhs.w - lhs.x * rhs.x - lhs.y * rhs.y - lhs.z * rhs.z};
}

Pose3d relativePose(const Pose3d & frame, const Pose3d & object)
{
  const auto orientation = normalized({frame.qx, frame.qy, frame.qz, frame.qw});
  const Quaternion inverse{-orientation.x, -orientation.y, -orientation.z, orientation.w};
  const Quaternion displacement{object.x - frame.x, object.y - frame.y, object.z - frame.z, 0.0};
  const auto rotated = multiply(multiply(inverse, displacement), orientation);
  const auto object_orientation = normalized({object.qx, object.qy, object.qz, object.qw});
  const auto relative_orientation = normalized(multiply(inverse, object_orientation));
  return {rotated.x,
          rotated.y,
          rotated.z,
          relative_orientation.x,
          relative_orientation.y,
          relative_orientation.z,
          relative_orientation.w};
}

void requireRelativePose(ValidationResult & result, const WorldSnapshot & before,
                         const WorldSnapshot & after, const PickPlaceContractConfig & config)
{
  if (!before.gazebo_coke_pose_world || !after.gazebo_coke_pose_world) {
    addFailure(result, FailureCategory::OBSERVATION, "CARRIED_RELATIVE_POSE_UNAVAILABLE",
               "Carrying recovery requires actual TCP and Gazebo Coke poses");
    return;
  }
  const auto before_relative = relativePose(before.tcp_pose_world, *before.gazebo_coke_pose_world);
  const auto after_relative = relativePose(after.tcp_pose_world, *after.gazebo_coke_pose_world);
  const double position_error = positionDistance(before_relative, after_relative);
  const double orientation_error = orientationDistance(before_relative, after_relative);
  result.metrics["carried_relative_position_error"] = position_error;
  result.metrics["carried_relative_orientation_error_rad"] = orientation_error;
  if (position_error > config.carried_relative_position_tolerance) {
    addFailure(result, FailureCategory::POSTCONDITION, "CARRIED_RELATIVE_POSITION_DRIFT",
               "TCP-to-Coke relative position changed during recovery motion");
  }
  if (orientation_error > config.carried_relative_orientation_tolerance_rad) {
    addFailure(result, FailureCategory::POSTCONDITION, "CARRIED_RELATIVE_ORIENTATION_DRIFT",
               "TCP-to-Coke relative orientation changed during recovery motion");
  }
}

void requireAttachmentsUnchanged(ValidationResult & result, const WorldSnapshot & before,
                                 const WorldSnapshot & after)
{
  if (!before.gazebo_coke_attached || !before.moveit_coke_attached || !after.gazebo_coke_attached ||
      !after.moveit_coke_attached || before.gazebo_coke_attached != after.gazebo_coke_attached ||
      before.moveit_coke_attached != after.moveit_coke_attached) {
    addFailure(result, FailureCategory::WORLD_INCONSISTENCY,
               "RECOVERY_ATTACHMENT_CHANGED_UNEXPECTEDLY",
               "This recovery action must not change attachment facts");
  }
}

void requireCrossWorldEquality(ValidationResult & result, const WorldSnapshot & snapshot,
                               const PickPlaceContractConfig & config)
{
  if (!snapshot.gazebo_coke_pose_world || snapshot.moveit_world_object_poses.count("coke") == 0) {
    addFailure(result, FailureCategory::WORLD_INCONSISTENCY, "CROSS_WORLD_COKE_POSE_UNAVAILABLE",
               "Detached recovery requires Gazebo and MoveIt Coke poses");
    return;
  }
  const auto & moveit_pose = snapshot.moveit_world_object_poses.at("coke");
  const double position_error = positionDistance(*snapshot.gazebo_coke_pose_world, moveit_pose);
  const double orientation_error =
    orientationDistance(*snapshot.gazebo_coke_pose_world, moveit_pose);
  result.metrics["gazebo_moveit_coke_position_error"] = position_error;
  result.metrics["gazebo_moveit_coke_orientation_error_rad"] = orientation_error;
  if (position_error > config.coke_position_tolerance ||
      orientation_error > config.coke_orientation_tolerance_rad) {
    addFailure(result, FailureCategory::WORLD_INCONSISTENCY, "CROSS_WORLD_COKE_POSE_MISMATCH",
               "Gazebo and MoveIt Coke poses differ beyond recovery tolerance");
  }
}

std::shared_ptr<const Contract> carriedMotionContract(const TargetPolicyPtr & target_policy,
                                                      const PickPlaceContractConfig & config,
                                                      State state, State next_state)
{
  return std::make_shared<FunctionalContract>(
    [config](const WorldSnapshot & before) {
      auto result = boundary(before);
      requireBothAttached(result, before);
      requireGrasp(result, before, config);
      return finish(std::move(result));
    },
    [target_policy, config, state, next_state](const WorldSnapshot & before,
                                               const WorldSnapshot & after,
                                               const ActionResult & action_result) {
      auto result = boundary(after);
      requireActionSucceeded(result, action_result);
      requireBothAttached(result, after);
      requireGrasp(result, after, config);
      requireTarget(result, after, target_policy, state, next_state, config);
      requireRelativePose(result, before, after, config);
      if (state == State::RECOVER_DESCEND_TO_PICK) {
        requireSupportedCoke(result, after, target_policy, State::DESCEND, State::CLOSE_GRIPPER,
                             config);
      }
      return finish(std::move(result));
    });
}

std::shared_ptr<const Contract> openContract(const PickPlaceContractConfig & config)
{
  return std::make_shared<FunctionalContract>(
    [](const WorldSnapshot & before) { return finish(boundary(before)); },
    [config](const WorldSnapshot & before, const WorldSnapshot & after,
             const ActionResult & action_result) {
      auto result = boundary(after);
      requireActionSucceeded(result, action_result);
      requireOpen(result, after, config);
      requireAttachmentsUnchanged(result, before, after);
      requireCokeDrift(result, before, after, config);
      return finish(std::move(result));
    });
}

std::shared_ptr<const Contract> gazeboDetachContract(const PickPlaceContractConfig & config)
{
  return std::make_shared<FunctionalContract>(
    [config](const WorldSnapshot & before) {
      auto result = boundary(before);
      requireOpen(result, before, config);
      return finish(std::move(result));
    },
    [config](const WorldSnapshot & before, const WorldSnapshot & after,
             const ActionResult & action_result) {
      auto result = boundary(after);
      requireActionSucceeded(result, action_result);
      requireOpen(result, after, config);
      if (after.gazebo_coke_attached && *after.gazebo_coke_attached) {
        addFailure(result, FailureCategory::GAZEBO_ATTACHMENT, "RECOVERY_GAZEBO_STILL_ATTACHED",
                   "Recovery Gazebo detach did not converge");
      }
      if (!before.moveit_coke_attached || !after.moveit_coke_attached ||
          before.moveit_coke_attached != after.moveit_coke_attached) {
        addFailure(result, FailureCategory::WORLD_INCONSISTENCY,
                   "RECOVERY_MOVEIT_ATTACHMENT_CHANGED",
                   "Gazebo detach must not change MoveIt attachment state");
      }
      requireCokeDrift(result, before, after, config);
      return finish(std::move(result));
    });
}

std::shared_ptr<const Contract> moveitDetachContract(const PickPlaceContractConfig & config)
{
  return std::make_shared<FunctionalContract>(
    [config](const WorldSnapshot & before) {
      auto result = boundary(before);
      requireOpen(result, before, config);
      if (!before.gazebo_coke_attached || *before.gazebo_coke_attached) {
        addFailure(result, FailureCategory::WORLD_INCONSISTENCY, "RECOVERY_GAZEBO_NOT_DETACHED",
                   "MoveIt recovery detach requires Gazebo already detached");
      }
      return finish(std::move(result));
    },
    [config](const WorldSnapshot & before, const WorldSnapshot & after,
             const ActionResult & action_result) {
      auto result = boundary(after);
      requireActionSucceeded(result, action_result);
      requireOpen(result, after, config);
      requireAttachmentCombination(result, after, false, false);
      requireWorldObjects(result, after);
      if (after.moveit_coke_attached_link || !after.moveit_coke_touch_links.empty()) {
        addFailure(result, FailureCategory::MOVEIT_SCENE,
                   "RECOVERY_MOVEIT_ATTACHED_METADATA_REMAINS",
                   "Detached Coke must not retain MoveIt attached metadata");
      }
      requireCokeDrift(result, before, after, config);
      return finish(std::move(result));
    });
}

std::shared_ptr<const Contract> syncContract(const PickPlaceContractConfig & config)
{
  return std::make_shared<FunctionalContract>(
    [config](const WorldSnapshot & before) {
      auto result = boundary(before);
      requireOpen(result, before, config);
      requireAttachmentCombination(result, before, false, false);
      requireWorldObjects(result, before);
      return finish(std::move(result));
    },
    [config](const WorldSnapshot & before, const WorldSnapshot & after,
             const ActionResult & action_result) {
      auto result = boundary(after);
      requireActionSucceeded(result, action_result);
      requireOpen(result, after, config);
      requireAttachmentCombination(result, after, false, false);
      requireWorldObjects(result, after);
      requireCrossWorldEquality(result, after, config);
      requireCokeDrift(result, before, after, config);
      return finish(std::move(result));
    });
}

std::shared_ptr<const Contract> retreatContract(const TargetPolicyPtr & target_policy,
                                                const PickPlaceContractConfig & config)
{
  return std::make_shared<FunctionalContract>(
    [config](const WorldSnapshot & before) {
      auto result = boundary(before);
      requireOpen(result, before, config);
      requireAttachmentCombination(result, before, false, false);
      requireWorldObjects(result, before);
      requireCrossWorldEquality(result, before, config);
      return finish(std::move(result));
    },
    [target_policy, config](const WorldSnapshot & before, const WorldSnapshot & after,
                            const ActionResult & action_result) {
      auto result = boundary(after);
      requireActionSucceeded(result, action_result);
      requireReadyAndClosed(result, after, config);
      requireAttachmentCombination(result, after, false, false);
      requireWorldObjects(result, after);
      requireCrossWorldEquality(result, after, config);
      requireCokeDrift(result, before, after, config);
      return finish(std::move(result));
    });
}

}  // namespace

void registerRecoveryContracts(TransitionContractRegistry & registry,
                               const TargetPolicyPtr & target_policy,
                               const PickPlaceContractConfig & config)
{
  registry.registerContract({State::RECOVER_LIFT_TO_SAFE_HEIGHT, State::RECOVER_MOVE_ABOVE_PICK},
                            carriedMotionContract(target_policy, config,
                                                  State::RECOVER_LIFT_TO_SAFE_HEIGHT,
                                                  State::RECOVER_MOVE_ABOVE_PICK));
  registry.registerContract({State::RECOVER_MOVE_ABOVE_PICK, State::RECOVER_DESCEND_TO_PICK},
                            carriedMotionContract(target_policy, config,
                                                  State::RECOVER_MOVE_ABOVE_PICK,
                                                  State::RECOVER_DESCEND_TO_PICK));
  registry.registerContract({State::RECOVER_DESCEND_TO_PICK, State::RECOVER_OPEN_GRIPPER},
                            carriedMotionContract(target_policy, config,
                                                  State::RECOVER_DESCEND_TO_PICK,
                                                  State::RECOVER_OPEN_GRIPPER));
  registry.registerContract({State::RECOVER_OPEN_GRIPPER, State::RECOVER_DETACH_GAZEBO},
                            openContract(config));
  registry.registerContract({State::RECOVER_DETACH_GAZEBO, State::RECOVER_DETACH_MOVEIT},
                            gazeboDetachContract(config));
  registry.registerContract({State::RECOVER_DETACH_MOVEIT, State::RECOVER_SYNC_WORLD_OBJECT},
                            moveitDetachContract(config));
  registry.registerContract({State::RECOVER_SYNC_WORLD_OBJECT, State::RECOVER_RETREAT},
                            syncContract(config));
  registry.registerContract({State::RECOVER_RETREAT, State::ERROR},
                            retreatContract(target_policy, config));
}

}  // namespace panda_gazebo_demo::pick_place
