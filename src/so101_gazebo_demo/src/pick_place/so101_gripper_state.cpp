#include "so101_gazebo_demo/pick_place/so101_gripper_state.hpp"

#include <algorithm>
#include <cmath>
#include <utility>

namespace so101_gazebo_demo::pick_place
{
namespace
{

std::pair<double, double> targetFor(SO101GripperTarget target, const SO101Profile & profile)
{
  switch (target) {
    case SO101GripperTarget::PREOPEN:
      return {profile.q6_preopen, profile.preopen_width};
    case SO101GripperTarget::CONTACT:
      return {profile.q6_contact, profile.contact_width};
    case SO101GripperTarget::FULL_OPEN:
      return {profile.q6_full_open, gripperWidthAtSection(profile.q6_full_open, profile)};
  }
  return {NAN, NAN};
}

ActionResult failure(ActionStatus status, FailureCategory category, std::string code,
                     std::string message)
{
  return {status, Failure{category, std::move(code), std::move(message), {}}};
}

ValidationResult validationFailure(FailureCategory category, std::string code,
                                   std::string message)
{
  return {false, {{category, std::move(code), std::move(message), {}}}, {}};
}

void append(ValidationResult & result, ValidationResult additional)
{
  result.metrics.insert(additional.metrics.begin(), additional.metrics.end());
  result.failures.insert(result.failures.end(), additional.failures.begin(),
                         additional.failures.end());
  result.ok = result.failures.empty();
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

void requireAttachmentEvidence(ValidationResult & result, const WorldSnapshot & world,
                               const SO101GripperStateConfig & config,
                               const SO101Profile & profile)
{
  const auto table = world.moveit_world_object_poses.find(profile.table_object);
  if (!world.gazebo_task_object_pose_world || !world.gazebo_task_object_stationary ||
      !*world.gazebo_task_object_stationary || !world.gazebo_task_object_attached ||
      !world.moveit_task_object_attached || table == world.moveit_world_object_poses.end()) {
    result.failures.push_back({FailureCategory::OBSERVATION,
                               "GRIPPER_ENVIRONMENT_EVIDENCE_INCOMPLETE",
                               "Gripper transitions require independent TaskObject and table evidence",
                               {}});
    return;
  }
  const auto exact_moveit_detached = [&]() {
    return !*world.moveit_task_object_attached &&
           world.moveit_world_object_poses.count(profile.task_object_id) == 1 &&
           !world.moveit_task_object_attached_link && world.moveit_task_object_touch_links.empty() &&
           !world.moveit_task_object_attached_relative_pose;
  };
  const std::set<std::string> touch_links(profile.moveit_touch_links.begin(),
                                          profile.moveit_touch_links.end());
  const auto exact_moveit_attached = [&]() {
    return *world.moveit_task_object_attached &&
           world.moveit_world_object_poses.count(profile.task_object_id) == 0 &&
           world.moveit_task_object_attached_link &&
           *world.moveit_task_object_attached_link == profile.moveit_attach_link &&
           world.moveit_task_object_touch_links == touch_links &&
           world.moveit_task_object_attached_relative_pose &&
           positionDistance(*world.moveit_task_object_attached_relative_pose,
                            profile.calibrated_grasp_relative_pose) <=
             profile.task_object_position_drift_tolerance &&
           orientationDistance(*world.moveit_task_object_attached_relative_pose,
                               profile.calibrated_grasp_relative_pose) <=
             profile.task_object_orientation_drift_tolerance_rad;
  };
  bool valid = false;
  if (config.state == State::PREPARE_OPEN_GRIPPER || config.state == State::CLOSE_GRIPPER) {
    valid = !*world.gazebo_task_object_attached && exact_moveit_detached();
  } else if (config.state == State::OPEN_GRIPPER) {
    valid = *world.gazebo_task_object_attached && exact_moveit_attached();
  } else {
    valid = *world.moveit_task_object_attached ? exact_moveit_attached()
                                        : exact_moveit_detached();
  }
  if (!valid) {
    result.failures.push_back({FailureCategory::WORLD_INCONSISTENCY,
                               "GRIPPER_ATTACHMENT_STATE_INVALID",
                               "Attachment facts do not match the gripper state's safety boundary",
                               {}});
  }
  result.ok = result.failures.empty();
}

class GripperContract final : public SO101Contract
{
public:
  GripperContract(SO101GripperStateConfig config, SO101Profile profile) :
      config_(config), profile_(std::move(profile))
  {
  }

  ValidationResult validatePrecondition(const WorldSnapshot & before) const override
  {
    if (!before.fresh) {
      return validationFailure(FailureCategory::OBSERVATION, "STALE_WORLD_SNAPSHOT",
                               "Gripper execution requires a fresh world observation");
    }
    if (!before.arm_stationary) {
      return validationFailure(FailureCategory::PRECONDITION, "ARM_NOT_QUIESCENT",
                               "The arm must be stationary before gripper execution");
    }
    const auto position = before.joint_positions.find(profile_.gripper_joint);
    const auto velocity = before.joint_velocities.find(profile_.gripper_joint);
    if (position == before.joint_positions.end() || velocity == before.joint_velocities.end() ||
        !std::isfinite(position->second) || !std::isfinite(velocity->second)) {
      return validationFailure(FailureCategory::GRIPPER, "Q6_EVIDENCE_INCOMPLETE",
                               "Finite joint 6 position and velocity are required");
    }
    if (std::abs(velocity->second) > profile_.q6_velocity_tolerance) {
      return validationFailure(FailureCategory::GRIPPER, "Q6_NOT_STATIONARY",
                               "Joint 6 must be stationary before a new command");
    }
    ValidationResult result{true, {}, {}};
    requireAttachmentEvidence(result, before, config_, profile_);
    return result;
  }

  ValidationResult validate(const WorldSnapshot & before, const WorldSnapshot & after,
                            const ActionResult & action) const override
  {
    ValidationResult result{true, {}, {}};
    if (action.status != ActionStatus::SUCCEEDED) {
      result.failures.push_back({FailureCategory::EXECUTION, "ACTION_DID_NOT_SUCCEED",
                                 "The gripper action did not report success", {}});
    }
    if (!after.arm_stationary) {
      result.failures.push_back({FailureCategory::POSTCONDITION, "ARM_NOT_QUIESCENT",
                                 "The arm must remain stationary after gripper execution", {}});
    }
    const auto [target_q6, target_width] = targetFor(config_.target, profile_);
    append(result, validateSO101GripperTarget(after, config_.target, profile_));
    requireAttachmentEvidence(result, after, config_, profile_);
    if (config_.state == State::PREPARE_OPEN_GRIPPER ||
        config_.state == State::CLOSE_GRIPPER ||
        config_.state == State::OPEN_GRIPPER ||
        config_.state == State::RECOVER_OPEN_GRIPPER) {
      if (!before.gazebo_task_object_pose_world || !after.gazebo_task_object_pose_world) {
        result.failures.push_back({FailureCategory::OBSERVATION, "GAZEBO_TASK_OBJECT_POSE_UNAVAILABLE",
                                   "TaskObject poses are required before and after close", {}});
      } else {
        const double position_drift =
          positionDistance(*before.gazebo_task_object_pose_world, *after.gazebo_task_object_pose_world);
        const double orientation_drift =
          orientationDistance(*before.gazebo_task_object_pose_world, *after.gazebo_task_object_pose_world);
        result.metrics["task_object_position_drift"] = position_drift;
        result.metrics["task_object_orientation_drift_rad"] = orientation_drift;
        if (position_drift > profile_.task_object_position_drift_tolerance) {
          result.failures.push_back({FailureCategory::POSTCONDITION, "TASK_OBJECT_POSITION_DRIFT",
                                     "Gripper motion moved TaskObject beyond the configured position tolerance",
                                     {}});
        }
        if (orientation_drift > profile_.task_object_orientation_drift_tolerance_rad) {
          result.failures.push_back(
            {FailureCategory::POSTCONDITION, "TASK_OBJECT_ORIENTATION_DRIFT",
             "Gripper motion rotated TaskObject beyond the configured orientation tolerance", {}});
        }
      }
      if (!after.gazebo_task_object_stationary || !*after.gazebo_task_object_stationary) {
        result.failures.push_back({FailureCategory::POSTCONDITION, "TASK_OBJECT_NOT_STATIONARY",
                                   "TaskObject must be stationary after close", {}});
      }
    }
    result.ok = result.failures.empty();
    for (auto & failure_item : result.failures) {
      failure_item.metrics.insert(result.metrics.begin(), result.metrics.end());
    }
    return result;
  }

private:
  SO101GripperStateConfig config_;
  SO101Profile profile_;
};

}  // namespace

SO101GripperStateExecutor::SO101GripperStateExecutor(
  std::shared_ptr<ISO101GripperCommand> command, SO101GripperStateConfig config,
  SO101Profile profile) :
    command_(std::move(command)), config_(config), profile_(std::move(profile))
{
}

ActionResult SO101GripperStateExecutor::execute(const ExecutionContext & context)
{
  if (context.state != config_.state) {
    return failure(ActionStatus::NOT_SUPPORTED, FailureCategory::GRIPPER,
                   "STATE_NOT_EXECUTABLE", "Gripper executor is configured for another state");
  }
  if (!command_) {
    return failure(ActionStatus::FAILED, FailureCategory::CONFIGURATION,
                   "GRIPPER_ADAPTER_MISSING", "Gripper executor has no command adapter");
  }
  const auto [target_q6, target_width] = targetFor(config_.target, profile_);
  if (config_.no_op_if_at_target &&
      validateSO101GripperTarget(context.before, config_.target, profile_).ok) {
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }
  return command_->command(
    config_.target == SO101GripperTarget::CONTACT ? profile_.q6_close : target_q6);
}

ValidationResult validateSO101GripperTarget(const WorldSnapshot & snapshot,
                                            SO101GripperTarget target,
                                            const SO101Profile & profile)
{
  if (target == SO101GripperTarget::CONTACT) {
    auto contact_profile = profile;
    contact_profile.q6_tolerance = profile.contact_q6_stop_tolerance;
    contact_profile.width_tolerance = profile.contact_width_oversize_tolerance;
    const auto [q6, width] = targetFor(target, profile);
    auto result = validateQ6Target(snapshot, q6, width, contact_profile);
    if (snapshot.gazebo_task_object_gripper_contact.value_or(false)) {
      result.failures.erase(
        std::remove_if(result.failures.begin(), result.failures.end(), [](const Failure & failure) {
          return failure.code == "Q6_TARGET_OUT_OF_TOLERANCE" ||
                 failure.code == "Q6_WIDTH_OUT_OF_TOLERANCE";
        }),
        result.failures.end());
      result.metrics["gazebo_task_object_gripper_contact"] = 1.0;
      if (snapshot.gazebo_task_object_gripper_max_depth) {
        result.metrics["gazebo_task_object_gripper_max_depth"] =
          *snapshot.gazebo_task_object_gripper_max_depth;
      }
      result.ok = result.failures.empty();
    }
    return result;
  }
  if (target == SO101GripperTarget::PREOPEN) {
    const auto [q6, width] = targetFor(target, profile);
    return validateQ6Target(snapshot, q6, width, profile);
  }
  const auto position = snapshot.joint_positions.find(profile.gripper_joint);
  const auto velocity = snapshot.joint_velocities.find(profile.gripper_joint);
  if (!snapshot.fresh || position == snapshot.joint_positions.end() ||
      velocity == snapshot.joint_velocities.end() || !std::isfinite(position->second) ||
      !std::isfinite(velocity->second)) {
    return validationFailure(FailureCategory::GRIPPER, "Q6_EVIDENCE_INCOMPLETE",
                             "Fresh finite joint 6 position and velocity are required");
  }
  ValidationResult result{true, {}, {{"expected_q6", profile.q6_full_open},
                                     {"actual_q6", position->second},
                                     {"actual_q6_velocity", velocity->second}}};
  if (std::abs(position->second - profile.q6_full_open) > profile.q6_full_open_tolerance) {
    result.failures.push_back({FailureCategory::GRIPPER, "Q6_TARGET_OUT_OF_TOLERANCE",
                               "Joint 6 is outside the full-open tolerance", {}});
  }
  if (std::abs(velocity->second) > profile.q6_velocity_tolerance) {
    result.failures.push_back({FailureCategory::GRIPPER, "Q6_NOT_STATIONARY",
                               "Joint 6 velocity exceeds the stop threshold", {}});
  }
  result.ok = result.failures.empty();
  return result;
}

ActionResult SO101GripperStateExecutor::cancel()
{
  if (!command_) {
    return failure(ActionStatus::FAILED, FailureCategory::CONFIGURATION,
                   "GRIPPER_ADAPTER_MISSING", "Gripper executor has no command adapter");
  }
  return command_->cancelAndWait();
}

std::shared_ptr<const SO101Contract> makeSO101GripperContract(SO101GripperStateConfig config,
                                                              SO101Profile profile)
{
  return std::make_shared<GripperContract>(config, std::move(profile));
}

}  // namespace so101_gazebo_demo::pick_place
