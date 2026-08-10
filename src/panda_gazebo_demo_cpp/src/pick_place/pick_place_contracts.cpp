#include "panda_gazebo_demo/pick_place/pick_place_contracts.hpp"

#include <algorithm>
#include <cmath>
#include <memory>
#include <optional>
#include <set>
#include <string>
#include <utility>

#include "pick_place_common/functional_transition_contract.hpp"
#include "pick_place_common/validation_result_utils.hpp"

namespace panda_gazebo_demo::pick_place
{
namespace
{

const std::set<std::string> kRequiredTouchLinks{"panda_hand", "panda_leftfinger",
                                                "panda_rightfinger"};

using pick_place_common::FunctionalTransitionContract;

ValidationResult resultFor(const WorldSnapshot & snapshot)
{
  ValidationResult result{true, {}, {}};
  result.metrics["snapshot_fresh"] = snapshot.fresh ? 1.0 : 0.0;
  result.metrics["arm_stationary"] = snapshot.arm_stationary ? 1.0 : 0.0;
  result.metrics["gripper_open"] = snapshot.gripper_open ? 1.0 : 0.0;
  result.metrics["gazebo_attached"] = snapshot.gazebo_task_object_attached
                                        ? (*snapshot.gazebo_task_object_attached ? 1.0 : 0.0)
                                        : -1.0;
  result.metrics["moveit_attached"] = snapshot.moveit_task_object_attached
                                        ? (*snapshot.moveit_task_object_attached ? 1.0 : 0.0)
                                        : -1.0;
  result.metrics["coke_stationary"] = snapshot.gazebo_task_object_stationary
                                        ? (*snapshot.gazebo_task_object_stationary ? 1.0 : 0.0)
                                        : -1.0;
  return result;
}

void requireFreshStationary(ValidationResult & result, const WorldSnapshot & snapshot,
                            FailureCategory category)
{
  if (!snapshot.fresh) {
    pick_place_common::appendFailure(result, FailureCategory::OBSERVATION, "STALE_WORLD_SNAPSHOT",
                                     "A fresh world observation is required");
  }
  if (!snapshot.arm_stationary) {
    pick_place_common::appendFailure(result, category, "ARM_NOT_QUIESCENT",
                                     "The arm must be stationary at the transition boundary");
  }
}

void requireActionSucceeded(ValidationResult & result, const ActionResult & action_result)
{
  result.metrics["action_succeeded"] = action_result.status == ActionStatus::SUCCEEDED ? 1.0 : 0.0;
  if (action_result.status != ActionStatus::SUCCEEDED) {
    pick_place_common::appendFailure(result, FailureCategory::EXECUTION, "ACTION_DID_NOT_SUCCEED",
                                     "The state action did not report success");
  }
}

void requireAttachments(ValidationResult & result, const WorldSnapshot & snapshot,
                        bool gazebo_attached, bool moveit_attached)
{
  pick_place_common::mergeValidationResult(
    result, validateAttachmentState(snapshot, gazebo_attached, moveit_attached));
}

void requireGripperOpen(ValidationResult & result, const WorldSnapshot & snapshot,
                        const PickPlaceContractConfig & config)
{
  pick_place_common::mergeValidationResult(result, validateGripperOpen(snapshot, config.gripper));
}

void requireGripperGrasp(ValidationResult & result, const WorldSnapshot & snapshot,
                         const PickPlaceContractConfig & config)
{
  pick_place_common::mergeValidationResult(result, validateGripperGrasp(snapshot, config.gripper));
}

void requireReadyAndClosed(ValidationResult & result, const WorldSnapshot & snapshot,
                           const PickPlaceContractConfig & config)
{
  pick_place_common::mergeValidationResult(
    result,
    validateNamedJointTarget(snapshot, config.ready_joint_positions, config.ready_joint_tolerance));
  pick_place_common::mergeValidationResult(
    result, validateGripperClosed(snapshot, config.gripper_close_position,
                                  config.gripper_close_tolerance, config.gripper));
}

void requireCokeStationary(ValidationResult & result, const WorldSnapshot & snapshot)
{
  if (!snapshot.gazebo_task_object_stationary || !*snapshot.gazebo_task_object_stationary) {
    pick_place_common::appendFailure(
      result, FailureCategory::POSTCONDITION, "COKE_NOT_STATIONARY",
      "Gazebo Coke must be observed stationary at the transition boundary");
  }
}

void requireWorldObjects(ValidationResult & result, const WorldSnapshot & snapshot)
{
  result.metrics["table_in_moveit_world"] =
    snapshot.moveit_world_object_poses.count("table") == 1 ? 1.0 : 0.0;
  result.metrics["coke_in_moveit_world"] =
    snapshot.moveit_world_object_poses.count("coke") == 1 ? 1.0 : 0.0;
  if (snapshot.moveit_world_object_poses.count("table") == 0) {
    pick_place_common::appendFailure(result, FailureCategory::MOVEIT_SCENE,
                                     "TABLE_MISSING_FROM_MOVEIT_WORLD",
                                     "MoveIt Planning Scene must contain the table");
  }
  if (snapshot.moveit_world_object_poses.count("coke") == 0) {
    pick_place_common::appendFailure(result, FailureCategory::MOVEIT_SCENE,
                                     "COKE_MISSING_FROM_MOVEIT_WORLD",
                                     "MoveIt Planning Scene must contain detached Coke");
  }
}

void requireTcpTarget(ValidationResult & result, const WorldSnapshot & snapshot,
                      const TargetPolicyPtr & target_policy, State state, State next_state,
                      const PickPlaceContractConfig & config)
{
  if (!target_policy) {
    pick_place_common::appendFailure(result, FailureCategory::CONFIGURATION,
                                     "TARGET_POLICY_MISSING",
                                     "Transition contract requires a target policy");
    return;
  }
  const auto target =
    target_policy->targetPose(state, next_state, ObservationResult{snapshot, std::nullopt});
  if (!target.target_pose) {
    result.failures.push_back(
      target.failure.value_or(Failure{FailureCategory::CONFIGURATION,
                                      "TARGET_POLICY_FAILED",
                                      "Target policy did not return a transition target",
                                      {}}));
    return;
  }
  const double position_error = positionDistance(snapshot.tcp_pose_world, *target.target_pose);
  const double orientation_error =
    orientationDistance(snapshot.tcp_pose_world, *target.target_pose);
  result.metrics["tcp_position_error"] = position_error;
  result.metrics["tcp_orientation_error_rad"] = orientation_error;
  if (position_error > config.tcp_position_tolerance) {
    pick_place_common::appendFailure(
      result, FailureCategory::POSTCONDITION, "TCP_POSITION_OUTSIDE_TOLERANCE",
      "TCP position is outside the configured transition target tolerance");
  }
  if (orientation_error > config.tcp_orientation_tolerance_rad) {
    pick_place_common::appendFailure(
      result, FailureCategory::POSTCONDITION, "TCP_ORIENTATION_OUTSIDE_TOLERANCE",
      "TCP orientation is outside the configured transition target tolerance");
  }
}

void requireCokeDrift(ValidationResult & result, const WorldSnapshot & before,
                      const WorldSnapshot & after, const PickPlaceContractConfig & config)
{
  if (!before.gazebo_task_object_pose_world || !after.gazebo_task_object_pose_world) {
    pick_place_common::appendFailure(
      result, FailureCategory::OBSERVATION, "GAZEBO_COKE_POSE_UNAVAILABLE",
      "Gazebo Coke poses are required on both sides of the transition");
    return;
  }
  const double position_drift =
    positionDistance(*before.gazebo_task_object_pose_world, *after.gazebo_task_object_pose_world);
  const double orientation_drift = orientationDistance(*before.gazebo_task_object_pose_world,
                                                       *after.gazebo_task_object_pose_world);
  result.metrics["coke_position_drift"] = position_drift;
  result.metrics["coke_orientation_drift_rad"] = orientation_drift;
  if (position_drift > config.coke_position_tolerance) {
    pick_place_common::appendFailure(result, FailureCategory::POSTCONDITION, "COKE_POSITION_DRIFT",
                                     "Coke position changed beyond the configured tolerance");
  }
  if (orientation_drift > config.coke_orientation_tolerance_rad) {
    pick_place_common::appendFailure(result, FailureCategory::POSTCONDITION,
                                     "COKE_ORIENTATION_DRIFT",
                                     "Coke orientation changed beyond the configured tolerance");
  }
}

void requireRelativePoseContinuity(ValidationResult & result, const WorldSnapshot & before,
                                   const WorldSnapshot & after,
                                   const PickPlaceContractConfig & config)
{
  if (!before.gazebo_task_object_pose_world || !after.gazebo_task_object_pose_world) {
    pick_place_common::appendFailure(
      result, FailureCategory::OBSERVATION, "CARRIED_RELATIVE_POSE_UNAVAILABLE",
      "Actual TCP and Gazebo Coke poses are required for carried-relative validation");
    return;
  }
  const auto before_relative =
    relativePose(before.tcp_pose_world, *before.gazebo_task_object_pose_world);
  const auto after_relative =
    relativePose(after.tcp_pose_world, *after.gazebo_task_object_pose_world);
  if (!before_relative || !after_relative) {
    pick_place_common::appendFailure(
      result, FailureCategory::OBSERVATION, "CARRIED_RELATIVE_POSE_UNAVAILABLE",
      "Actual TCP and Gazebo Coke poses must contain usable quaternions");
    return;
  }
  const double position_error = positionDistance(*before_relative, *after_relative);
  const double orientation_error = orientationDistance(*before_relative, *after_relative);
  result.metrics["carried_relative_position_error"] = position_error;
  result.metrics["carried_relative_orientation_error_rad"] = orientation_error;
  if (position_error > config.carried_relative_position_tolerance) {
    pick_place_common::appendFailure(
      result, FailureCategory::POSTCONDITION, "CARRIED_RELATIVE_POSITION_DRIFT",
      "Actual TCP-to-Coke relative position changed beyond tolerance");
  }
  if (orientation_error > config.carried_relative_orientation_tolerance_rad) {
    pick_place_common::appendFailure(
      result, FailureCategory::POSTCONDITION, "CARRIED_RELATIVE_ORIENTATION_DRIFT",
      "Actual TCP-to-Coke relative orientation changed beyond tolerance");
  }
}

void requireExactAttachedMetadata(ValidationResult & result, const WorldSnapshot & snapshot)
{
  const bool exact_link = snapshot.moveit_task_object_attached_link &&
                          *snapshot.moveit_task_object_attached_link == "panda_hand";
  result.metrics["moveit_attached_link_exact"] = exact_link ? 1.0 : 0.0;
  result.metrics["moveit_touch_link_count"] =
    static_cast<double>(snapshot.moveit_task_object_touch_links.size());
  result.metrics["moveit_touch_links_exact"] =
    snapshot.moveit_task_object_touch_links == kRequiredTouchLinks ? 1.0 : 0.0;
  if (!exact_link) {
    pick_place_common::appendFailure(result, FailureCategory::MOVEIT_SCENE,
                                     "MOVEIT_ATTACHED_LINK_MISMATCH",
                                     "MoveIt Coke must be attached exactly to panda_hand");
  }
  if (snapshot.moveit_task_object_touch_links != kRequiredTouchLinks) {
    pick_place_common::appendFailure(
      result, FailureCategory::MOVEIT_SCENE, "MOVEIT_TOUCH_LINKS_MISMATCH",
      "MoveIt Coke touch links must be panda_hand and both fingers exactly");
  }
  if (snapshot.moveit_world_object_poses.count("coke") != 0) {
    pick_place_common::appendFailure(
      result, FailureCategory::MOVEIT_SCENE, "MOVEIT_COKE_IN_BOTH_SETS",
      "Attached Coke must be absent from the MoveIt world object set");
  }
}

void requireCrossWorldEquality(ValidationResult & result, const WorldSnapshot & snapshot,
                               const PickPlaceContractConfig & config)
{
  if (!snapshot.gazebo_task_object_pose_world ||
      snapshot.moveit_world_object_poses.count("coke") == 0) {
    pick_place_common::appendFailure(result, FailureCategory::WORLD_INCONSISTENCY,
                                     "CROSS_WORLD_COKE_POSE_UNAVAILABLE",
                                     "Gazebo and MoveIt Coke world poses are both required");
    return;
  }
  const auto & moveit_pose = snapshot.moveit_world_object_poses.at("coke");
  const double position_error =
    positionDistance(*snapshot.gazebo_task_object_pose_world, moveit_pose);
  const double orientation_error =
    orientationDistance(*snapshot.gazebo_task_object_pose_world, moveit_pose);
  result.metrics["gazebo_moveit_coke_position_error"] = position_error;
  result.metrics["gazebo_moveit_coke_orientation_error_rad"] = orientation_error;
  if (position_error > config.coke_position_tolerance) {
    pick_place_common::appendFailure(result, FailureCategory::WORLD_INCONSISTENCY,
                                     "CROSS_WORLD_COKE_POSITION_MISMATCH",
                                     "Gazebo and MoveIt Coke positions differ beyond tolerance");
  }
  if (orientation_error > config.coke_orientation_tolerance_rad) {
    pick_place_common::appendFailure(result, FailureCategory::WORLD_INCONSISTENCY,
                                     "CROSS_WORLD_COKE_ORIENTATION_MISMATCH",
                                     "Gazebo and MoveIt Coke orientations differ beyond tolerance");
  }
}

void requireSupportedCoke(ValidationResult & result, const WorldSnapshot & snapshot,
                          const TargetPolicyPtr & target_policy, State state, State next_state,
                          const PickPlaceContractConfig & config)
{
  if (!snapshot.gazebo_task_object_pose_world) {
    pick_place_common::appendFailure(result, FailureCategory::OBSERVATION,
                                     "GAZEBO_COKE_POSE_UNAVAILABLE",
                                     "Gazebo Coke pose is required for place support validation");
    return;
  }
  if (!target_policy) {
    pick_place_common::appendFailure(result, FailureCategory::CONFIGURATION,
                                     "TARGET_POLICY_MISSING",
                                     "Coke support validation requires a target policy");
    return;
  }
  const auto expected =
    supportedCokePose(*target_policy, state, next_state, ObservationResult{snapshot, std::nullopt});
  if (!expected.target_pose) {
    result.failures.push_back(
      expected.failure.value_or(Failure{FailureCategory::CONFIGURATION,
                                        "SUPPORTED_COKE_TARGET_MISSING",
                                        "Target policy did not return a supported Coke pose",
                                        {}}));
    return;
  }
  const double position_error =
    positionDistance(*snapshot.gazebo_task_object_pose_world, *expected.target_pose);
  const double orientation_error =
    orientationDistance(*snapshot.gazebo_task_object_pose_world, *expected.target_pose);
  result.metrics["supported_coke_position_error"] = position_error;
  result.metrics["supported_coke_orientation_error_rad"] = orientation_error;
  if (position_error > config.coke_position_tolerance ||
      orientation_error > config.coke_orientation_tolerance_rad) {
    pick_place_common::appendFailure(
      result, FailureCategory::POSTCONDITION, "COKE_NOT_AT_SUPPORTED_PLACE_POSE",
      "Coke is outside the supported position or upright orientation");
  }
}

ValidationResult carryingBoundary(const WorldSnapshot & snapshot,
                                  const PickPlaceContractConfig & config, bool require_open)
{
  auto result = resultFor(snapshot);
  requireFreshStationary(result, snapshot, FailureCategory::PRECONDITION);
  requireAttachments(result, snapshot, true, true);
  requireExactAttachedMetadata(result, snapshot);
  if (require_open) {
    requireGripperOpen(result, snapshot, config);
  } else {
    requireGripperGrasp(result, snapshot, config);
  }
  return pick_place_common::finalizeValidationResult(std::move(result));
}

std::shared_ptr<const Contract> makeCarriedMotionContract(const TargetPolicyPtr & target_policy,
                                                          const PickPlaceContractConfig & config,
                                                          State start_state, State start_next,
                                                          State end_state, State end_next,
                                                          bool require_supported_place)
{
  return std::make_shared<FunctionalTransitionContract>(
    [target_policy, config, start_state, start_next](const WorldSnapshot & before) {
      auto result = carryingBoundary(before, config, false);
      requireTcpTarget(result, before, target_policy, start_state, start_next, config);
      return pick_place_common::finalizeValidationResult(std::move(result));
    },
    [target_policy, config, end_state, end_next,
     require_supported_place](const WorldSnapshot & before, const WorldSnapshot & after,
                              const ActionResult & action_result) {
      auto result = carryingBoundary(after, config, false);
      requireActionSucceeded(result, action_result);
      requireTcpTarget(result, after, target_policy, end_state, end_next, config);
      requireRelativePoseContinuity(result, before, after, config);
      if (require_supported_place) {
        requireSupportedCoke(result, after, target_policy, State::DESCEND_TO_PLACE,
                             State::OPEN_GRIPPER, config);
      }
      return pick_place_common::finalizeValidationResult(std::move(result));
    });
}

}  // namespace

std::shared_ptr<const Contract>
makeCloseToGazeboAttachContract(const TargetPolicyPtr & target_policy,
                                const PickPlaceContractConfig & config)
{
  return std::make_shared<FunctionalTransitionContract>(
    [target_policy, config](const WorldSnapshot & before) {
      auto result = resultFor(before);
      requireFreshStationary(result, before, FailureCategory::PRECONDITION);
      requireTcpTarget(result, before, target_policy, State::DESCEND, State::CLOSE_GRIPPER, config);
      requireAttachments(result, before, false, false);
      requireCokeStationary(result, before);
      requireWorldObjects(result, before);
      return pick_place_common::finalizeValidationResult(std::move(result));
    },
    [target_policy, config](const WorldSnapshot & before, const WorldSnapshot & after,
                            const ActionResult & action_result) {
      auto result = resultFor(after);
      requireActionSucceeded(result, action_result);
      requireFreshStationary(result, after, FailureCategory::POSTCONDITION);
      requireTcpTarget(result, after, target_policy, State::DESCEND, State::CLOSE_GRIPPER, config);
      requireAttachments(result, after, false, false);
      requireGripperGrasp(result, after, config);
      requireCokeStationary(result, after);
      requireCokeDrift(result, before, after, config);
      requireWorldObjects(result, after);
      return pick_place_common::finalizeValidationResult(std::move(result));
    });
}

std::shared_ptr<const Contract>
makeGazeboToMoveItAttachContract(const PickPlaceContractConfig & config)
{
  return std::make_shared<FunctionalTransitionContract>(
    [config](const WorldSnapshot & before) {
      auto result = resultFor(before);
      requireFreshStationary(result, before, FailureCategory::PRECONDITION);
      requireAttachments(result, before, false, false);
      requireGripperGrasp(result, before, config);
      requireCokeStationary(result, before);
      return pick_place_common::finalizeValidationResult(std::move(result));
    },
    [config](const WorldSnapshot & before, const WorldSnapshot & after,
             const ActionResult & action_result) {
      auto result = resultFor(after);
      requireActionSucceeded(result, action_result);
      requireFreshStationary(result, after, FailureCategory::POSTCONDITION);
      requireAttachments(result, after, true, false);
      requireGripperGrasp(result, after, config);
      requireCokeDrift(result, before, after, config);
      requireRelativePoseContinuity(result, before, after, config);
      return pick_place_common::finalizeValidationResult(std::move(result));
    });
}

std::shared_ptr<const Contract>
makeMoveItAttachToLiftContract(const PickPlaceContractConfig & config)
{
  return std::make_shared<FunctionalTransitionContract>(
    [config](const WorldSnapshot & before) {
      auto result = resultFor(before);
      requireFreshStationary(result, before, FailureCategory::PRECONDITION);
      requireAttachments(result, before, true, false);
      requireGripperGrasp(result, before, config);
      return pick_place_common::finalizeValidationResult(std::move(result));
    },
    [config](const WorldSnapshot & before, const WorldSnapshot & after,
             const ActionResult & action_result) {
      auto result = resultFor(after);
      requireActionSucceeded(result, action_result);
      requireFreshStationary(result, after, FailureCategory::POSTCONDITION);
      requireAttachments(result, after, true, true);
      requireGripperGrasp(result, after, config);
      requireExactAttachedMetadata(result, after);
      requireRelativePoseContinuity(result, before, after, config);
      return pick_place_common::finalizeValidationResult(std::move(result));
    });
}

std::shared_ptr<const Contract>
makeLiftToMoveAbovePlaceContract(const TargetPolicyPtr & target_policy,
                                 const PickPlaceContractConfig & config)
{
  return makeCarriedMotionContract(target_policy, config, State::DESCEND, State::CLOSE_GRIPPER,
                                   State::LIFT, State::MOVE_ABOVE_PLACE, false);
}

std::shared_ptr<const Contract>
makeMoveAbovePlaceToDescendContract(const TargetPolicyPtr & target_policy,
                                    const PickPlaceContractConfig & config)
{
  return makeCarriedMotionContract(target_policy, config, State::LIFT, State::MOVE_ABOVE_PLACE,
                                   State::MOVE_ABOVE_PLACE, State::DESCEND_TO_PLACE, false);
}

std::shared_ptr<const Contract>
makeDescendPlaceToOpenContract(const TargetPolicyPtr & target_policy,
                               const PickPlaceContractConfig & config)
{
  return makeCarriedMotionContract(target_policy, config, State::MOVE_ABOVE_PLACE,
                                   State::DESCEND_TO_PLACE, State::DESCEND_TO_PLACE,
                                   State::OPEN_GRIPPER, true);
}

std::shared_ptr<const Contract>
makeOpenToGazeboDetachContract(const TargetPolicyPtr & target_policy,
                               const PickPlaceContractConfig & config)
{
  return std::make_shared<FunctionalTransitionContract>(
    [target_policy, config](const WorldSnapshot & before) {
      auto result = carryingBoundary(before, config, false);
      requireTcpTarget(result, before, target_policy, State::DESCEND_TO_PLACE, State::OPEN_GRIPPER,
                       config);
      requireSupportedCoke(result, before, target_policy, State::DESCEND_TO_PLACE,
                           State::OPEN_GRIPPER, config);
      return pick_place_common::finalizeValidationResult(std::move(result));
    },
    [target_policy, config](const WorldSnapshot & before, const WorldSnapshot & after,
                            const ActionResult & action_result) {
      auto result = carryingBoundary(after, config, true);
      requireActionSucceeded(result, action_result);
      requireTcpTarget(result, after, target_policy, State::DESCEND_TO_PLACE, State::OPEN_GRIPPER,
                       config);
      requireSupportedCoke(result, after, target_policy, State::DESCEND_TO_PLACE,
                           State::OPEN_GRIPPER, config);
      requireCokeDrift(result, before, after, config);
      requireRelativePoseContinuity(result, before, after, config);
      return pick_place_common::finalizeValidationResult(std::move(result));
    });
}

std::shared_ptr<const Contract>
makeGazeboToMoveItDetachContract(const TargetPolicyPtr & target_policy,
                                 const PickPlaceContractConfig & config)
{
  return std::make_shared<FunctionalTransitionContract>(
    [target_policy, config](const WorldSnapshot & before) {
      auto result = carryingBoundary(before, config, true);
      requireSupportedCoke(result, before, target_policy, State::DESCEND_TO_PLACE,
                           State::OPEN_GRIPPER, config);
      return pick_place_common::finalizeValidationResult(std::move(result));
    },
    [target_policy, config](const WorldSnapshot & before, const WorldSnapshot & after,
                            const ActionResult & action_result) {
      auto result = resultFor(after);
      requireActionSucceeded(result, action_result);
      requireFreshStationary(result, after, FailureCategory::POSTCONDITION);
      requireAttachments(result, after, false, true);
      requireGripperOpen(result, after, config);
      requireCokeStationary(result, after);
      requireSupportedCoke(result, after, target_policy, State::DESCEND_TO_PLACE,
                           State::OPEN_GRIPPER, config);
      requireCokeDrift(result, before, after, config);
      return pick_place_common::finalizeValidationResult(std::move(result));
    });
}

std::shared_ptr<const Contract>
makeMoveItDetachToSyncContract(const TargetPolicyPtr & target_policy,
                               const PickPlaceContractConfig & config)
{
  return std::make_shared<FunctionalTransitionContract>(
    [target_policy, config](const WorldSnapshot & before) {
      auto result = resultFor(before);
      requireFreshStationary(result, before, FailureCategory::PRECONDITION);
      requireAttachments(result, before, false, true);
      requireGripperOpen(result, before, config);
      requireCokeStationary(result, before);
      requireSupportedCoke(result, before, target_policy, State::DESCEND_TO_PLACE,
                           State::OPEN_GRIPPER, config);
      return pick_place_common::finalizeValidationResult(std::move(result));
    },
    [target_policy, config](const WorldSnapshot &, const WorldSnapshot & after,
                            const ActionResult & action_result) {
      auto result = resultFor(after);
      requireActionSucceeded(result, action_result);
      requireFreshStationary(result, after, FailureCategory::POSTCONDITION);
      requireAttachments(result, after, false, false);
      requireGripperOpen(result, after, config);
      requireCokeStationary(result, after);
      requireSupportedCoke(result, after, target_policy, State::DESCEND_TO_PLACE,
                           State::OPEN_GRIPPER, config);
      requireWorldObjects(result, after);
      return pick_place_common::finalizeValidationResult(std::move(result));
    });
}

std::shared_ptr<const Contract> makeSyncToRetreatContract(const TargetPolicyPtr & target_policy,
                                                          const PickPlaceContractConfig & config)
{
  return std::make_shared<FunctionalTransitionContract>(
    [target_policy, config](const WorldSnapshot & before) {
      auto result = resultFor(before);
      requireFreshStationary(result, before, FailureCategory::PRECONDITION);
      requireAttachments(result, before, false, false);
      requireGripperOpen(result, before, config);
      requireCokeStationary(result, before);
      requireTcpTarget(result, before, target_policy, State::DESCEND_TO_PLACE, State::OPEN_GRIPPER,
                       config);
      requireSupportedCoke(result, before, target_policy, State::DESCEND_TO_PLACE,
                           State::OPEN_GRIPPER, config);
      requireWorldObjects(result, before);
      return pick_place_common::finalizeValidationResult(std::move(result));
    },
    [target_policy, config](const WorldSnapshot & before, const WorldSnapshot & after,
                            const ActionResult & action_result) {
      auto result = resultFor(after);
      requireActionSucceeded(result, action_result);
      requireFreshStationary(result, after, FailureCategory::POSTCONDITION);
      requireAttachments(result, after, false, false);
      requireGripperOpen(result, after, config);
      requireCokeStationary(result, after);
      requireTcpTarget(result, after, target_policy, State::DESCEND_TO_PLACE, State::OPEN_GRIPPER,
                       config);
      requireSupportedCoke(result, after, target_policy, State::DESCEND_TO_PLACE,
                           State::OPEN_GRIPPER, config);
      requireWorldObjects(result, after);
      requireCrossWorldEquality(result, after, config);
      requireCokeDrift(result, before, after, config);
      return pick_place_common::finalizeValidationResult(std::move(result));
    });
}

std::shared_ptr<const Contract> makeRetreatToDoneContract(const TargetPolicyPtr & target_policy,
                                                          const PickPlaceContractConfig & config)
{
  return std::make_shared<FunctionalTransitionContract>(
    [target_policy, config](const WorldSnapshot & before) {
      auto result = resultFor(before);
      requireFreshStationary(result, before, FailureCategory::PRECONDITION);
      requireAttachments(result, before, false, false);
      requireGripperOpen(result, before, config);
      requireCokeStationary(result, before);
      requireTcpTarget(result, before, target_policy, State::DESCEND_TO_PLACE, State::OPEN_GRIPPER,
                       config);
      requireSupportedCoke(result, before, target_policy, State::DESCEND_TO_PLACE,
                           State::OPEN_GRIPPER, config);
      requireWorldObjects(result, before);
      requireCrossWorldEquality(result, before, config);
      return pick_place_common::finalizeValidationResult(std::move(result));
    },
    [target_policy, config](const WorldSnapshot & before, const WorldSnapshot & after,
                            const ActionResult & action_result) {
      auto result = resultFor(after);
      requireActionSucceeded(result, action_result);
      requireFreshStationary(result, after, FailureCategory::POSTCONDITION);
      requireAttachments(result, after, false, false);
      requireReadyAndClosed(result, after, config);
      requireCokeStationary(result, after);
      requireSupportedCoke(result, after, target_policy, State::DESCEND_TO_PLACE,
                           State::OPEN_GRIPPER, config);
      requireWorldObjects(result, after);
      requireCrossWorldEquality(result, after, config);
      requireCokeDrift(result, before, after, config);
      return pick_place_common::finalizeValidationResult(std::move(result));
    });
}

void registerPickPlaceForwardContracts(TransitionContractRegistry & registry,
                                       const TargetPolicyPtr & target_policy,
                                       const PickPlaceContractConfig & config)
{
  registry.registerContract({State::CLOSE_GRIPPER, State::ATTACH_GAZEBO},
                            makeCloseToGazeboAttachContract(target_policy, config));
  registry.registerContract({State::ATTACH_GAZEBO, State::ATTACH_MOVEIT},
                            makeGazeboToMoveItAttachContract(config));
  registry.registerContract({State::ATTACH_MOVEIT, State::LIFT},
                            makeMoveItAttachToLiftContract(config));
  registry.registerContract({State::LIFT, State::MOVE_ABOVE_PLACE},
                            makeLiftToMoveAbovePlaceContract(target_policy, config));
  registry.registerContract({State::MOVE_ABOVE_PLACE, State::DESCEND_TO_PLACE},
                            makeMoveAbovePlaceToDescendContract(target_policy, config));
  registry.registerContract({State::DESCEND_TO_PLACE, State::OPEN_GRIPPER},
                            makeDescendPlaceToOpenContract(target_policy, config));
  registry.registerContract({State::OPEN_GRIPPER, State::DETACH_GAZEBO},
                            makeOpenToGazeboDetachContract(target_policy, config));
  registry.registerContract({State::DETACH_GAZEBO, State::DETACH_MOVEIT},
                            makeGazeboToMoveItDetachContract(target_policy, config));
  registry.registerContract({State::DETACH_MOVEIT, State::SYNC_WORLD_OBJECT},
                            makeMoveItDetachToSyncContract(target_policy, config));
  registry.registerContract({State::SYNC_WORLD_OBJECT, State::RETREAT},
                            makeSyncToRetreatContract(target_policy, config));
  registry.registerContract({State::RETREAT, State::DONE},
                            makeRetreatToDoneContract(target_policy, config));
}

}  // namespace panda_gazebo_demo::pick_place
