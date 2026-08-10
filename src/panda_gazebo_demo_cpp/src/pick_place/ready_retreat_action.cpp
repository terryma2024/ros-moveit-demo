#include "panda_gazebo_demo/pick_place/ready_retreat_action.hpp"

#include <algorithm>
#include <cmath>
#include <utility>

namespace panda_gazebo_demo::pick_place
{
namespace
{

ActionResult failure(FailureCategory category, std::string code, std::string message)
{
  return {ActionStatus::FAILED, Failure{category, std::move(code), std::move(message), {}}};
}

bool configuredTransition(const ReadyRetreatConfig & config, State state, State next_state)
{
  return config.state == state && config.next_state == next_state;
}

bool typedEvidenceMatches(const MotionPlanEvidence & evidence, const ReadyRetreatConfig & config)
{
  return evidence.state == config.state && evidence.next_state == config.next_state &&
         evidence.kind == MotionKind::NAMED_TARGET && evidence.named_target &&
         *evidence.named_target == config.named_target &&
         evidence.target_joint_positions == config.ready_joint_positions;
}

}  // namespace

ReadyRetreatAction::ReadyRetreatAction(std::shared_ptr<IMoveItMotionAdapter> motion,
                                       std::shared_ptr<IGripperCommandAdapter> gripper,
                                       std::shared_ptr<IWorldObserver> observer,
                                       ReadyRetreatConfig config) :
    motion_(std::move(motion)), gripper_(std::move(gripper)), observer_(std::move(observer)),
    config_(std::move(config))
{
}

PlanResult ReadyRetreatAction::plan(State current_state, State next_state,
                                    const ObservationResult & observation)
{
  if (!configuredTransition(config_, current_state, next_state)) {
    return {{ActionStatus::NOT_SUPPORTED,
             Failure{FailureCategory::PLANNING,
                     "READY_RETREAT_TRANSITION_NOT_PLANNABLE",
                     "Ready retreat planner received an unsupported transition",
                     {}}},
            nullptr};
  }
  if (!motion_) {
    return {{ActionStatus::FAILED, Failure{FailureCategory::CONFIGURATION,
                                           "READY_RETREAT_MOTION_ADAPTER_MISSING",
                                           "Ready retreat planner requires a MoveIt motion adapter",
                                           {}}},
            nullptr};
  }
  if (config_.named_target.empty() || config_.ready_joint_positions.empty() ||
      !std::isfinite(config_.clearance_height)) {
    return {
      {ActionStatus::FAILED, Failure{FailureCategory::CONFIGURATION,
                                     "READY_RETREAT_TARGET_MISSING",
                                     "Ready retreat planner requires a resolved named joint target",
                                     {}}},
      nullptr};
  }
  if (!observation.snapshot) {
    return {
      {ActionStatus::FAILED, Failure{FailureCategory::OBSERVATION,
                                     "READY_RETREAT_OBSERVATION_MISSING",
                                     "Ready retreat planning requires a current world observation",
                                     {}}},
      nullptr};
  }
  auto clearance_pose = observation.snapshot->tcp_pose_world;
  clearance_pose.z = std::max(clearance_pose.z, config_.clearance_height);
  return motion_->planSafeNamedTarget(
    {current_state, next_state, clearance_pose, config_.named_target}, observation);
}

ActionResult ReadyRetreatAction::execute(const ExecutionContext & context)
{
  if (!configuredTransition(config_, context.state, context.next_state)) {
    return failure(FailureCategory::EXECUTION, "READY_RETREAT_TRANSITION_NOT_EXECUTABLE",
                   "Ready retreat executor received an unsupported transition");
  }
  if (!motion_) {
    return failure(FailureCategory::CONFIGURATION, "READY_RETREAT_MOTION_ADAPTER_MISSING",
                   "Ready retreat executor requires a MoveIt motion adapter");
  }
  if (!gripper_) {
    return failure(FailureCategory::CONFIGURATION, "READY_RETREAT_GRIPPER_ADAPTER_MISSING",
                   "Ready retreat executor requires a gripper command adapter");
  }
  if (!observer_) {
    return failure(FailureCategory::CONFIGURATION, "READY_RETREAT_OBSERVER_MISSING",
                   "Ready retreat executor requires a physical world observer");
  }
  const auto evidence = std::dynamic_pointer_cast<const MotionPlanEvidence>(context.plan);
  if (!evidence || !typedEvidenceMatches(*evidence, config_)) {
    return failure(FailureCategory::EXECUTION, "INVALID_READY_RETREAT_PLAN_ARTIFACT",
                   "Ready retreat execution requires its typed named-target plan evidence");
  }
  auto motion_result = motion_->execute(*evidence);
  if (motion_result.status != ActionStatus::SUCCEEDED) {
    return motion_result;
  }
  const auto observation = observer_->observe();
  if (!observation.snapshot) {
    return failure(FailureCategory::OBSERVATION, "READY_RETREAT_OBSERVATION_MISSING",
                   "Ready retreat requires a post-motion physical observation");
  }
  if (!observation.snapshot->fresh || !observation.snapshot->arm_stationary) {
    return failure(FailureCategory::POSTCONDITION, "READY_RETREAT_ARM_NOT_READY",
                   "Arm must be freshly observed stationary before closing the gripper");
  }
  const auto ready = validateNamedJointTarget(*observation.snapshot, config_.ready_joint_positions,
                                              config_.joint_tolerance);
  if (!ready.ok) {
    return failure(
      FailureCategory::POSTCONDITION, "READY_RETREAT_ARM_NOT_READY",
      "Arm did not reach the configured ready joint target before closing the gripper");
  }
  return gripper_->command(config_.close_position, config_.max_effort);
}

ActionResult ReadyRetreatAction::cancel()
{
  if (!motion_) {
    return failure(FailureCategory::CONFIGURATION, "READY_RETREAT_MOTION_ADAPTER_MISSING",
                   "Ready retreat cancellation requires a MoveIt motion adapter");
  }
  if (!gripper_) {
    return failure(FailureCategory::CONFIGURATION, "READY_RETREAT_GRIPPER_ADAPTER_MISSING",
                   "Ready retreat cancellation requires a gripper command adapter");
  }
  auto motion_result = motion_->cancel();
  auto gripper_result = gripper_->cancelAndWait();
  if (motion_result.status != ActionStatus::SUCCEEDED) {
    return motion_result;
  }
  return gripper_result;
}

}  // namespace panda_gazebo_demo::pick_place
