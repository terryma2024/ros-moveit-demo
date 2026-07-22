#include "panda_gazebo_demo/pick_place/motion_state_action.hpp"

#include <memory>
#include <string>
#include <utility>

#include "panda_gazebo_demo/pick_place/state_validation.hpp"

namespace panda_gazebo_demo::pick_place
{
namespace
{

PlanResult planningFailure(
  ActionStatus status, FailureCategory category, std::string code,
  std::string message)
{
  return {{status, Failure{category, std::move(code), std::move(message), {}}}, nullptr};
}

ActionResult executionFailure(std::string code, std::string message)
{
  return {ActionStatus::FAILED, Failure{FailureCategory::EXECUTION,
      std::move(code), std::move(message), {}}};
}

bool recoveryRetreatPostconditionSatisfied(
  const WorldSnapshot & snapshot, const Pose3d & target)
{
  if (!snapshot.fresh || !snapshot.arm_stationary ||
    !snapshot.gazebo_coke_attached || *snapshot.gazebo_coke_attached ||
    !snapshot.moveit_coke_attached || *snapshot.moveit_coke_attached ||
    !snapshot.gazebo_coke_pose_world || !snapshot.gazebo_coke_stationary ||
    !*snapshot.gazebo_coke_stationary ||
    snapshot.moveit_world_object_poses.count("table") == 0 ||
    snapshot.moveit_world_object_poses.count("coke") == 0 ||
    !validateGripperOpen(snapshot, {}).ok)
  {
    return false;
  }
  const auto & moveit_coke = snapshot.moveit_world_object_poses.at("coke");
  return positionDistance(snapshot.tcp_pose_world, target) <= 0.005 &&
         orientationDistance(snapshot.tcp_pose_world, target) <= 0.035 &&
         positionDistance(*snapshot.gazebo_coke_pose_world, moveit_coke) <= 0.003 &&
         orientationDistance(*snapshot.gazebo_coke_pose_world, moveit_coke) <= 0.035;
}

PlanResult noOpPlan(
  const MotionStateConfig & config, const Pose3d & current_pose)
{
  auto evidence = std::make_shared<MotionPlanEvidence>();
  evidence->state = config.state;
  evidence->next_state = config.next_state;
  evidence->kind = config.kind;
  evidence->carrying = config.carrying;
  evidence->cartesian_fraction = 1.0;
  evidence->duration_seconds = 1.0e-6;
  evidence->start_tcp_pose = current_pose;
  evidence->end_tcp_pose = current_pose;
  evidence->tcp_path = {current_pose};
  evidence->trajectory_points = 1;
  evidence->collision_aware = true;
  evidence->no_op = true;
  return {{ActionStatus::SUCCEEDED, std::nullopt}, std::move(evidence)};
}

}  // namespace

MotionStateAction::MotionStateAction(
  std::shared_ptr<IMoveItMotionAdapter> adapter,
  std::shared_ptr<const PickPlaceTargetPolicy> target_policy,
  MotionStateConfig config)
: adapter_(std::move(adapter)), target_policy_(std::move(target_policy)), config_(config)
{
}

PlanResult MotionStateAction::plan(
  State current_state, State next_state,
  const ObservationResult & observation)
{
  if (current_state != config_.state || next_state != config_.next_state) {
    return planningFailure(ActionStatus::NOT_SUPPORTED, FailureCategory::PLANNING,
      "MOTION_TRANSITION_NOT_CONFIGURED",
      std::string("Motion action for ") + toString(config_.state) + " -> " +
      toString(config_.next_state) + " cannot plan " + toString(current_state) + " -> " +
      toString(next_state));
  }
  if (!adapter_) {
    return planningFailure(ActionStatus::FAILED, FailureCategory::CONFIGURATION,
      "MOTION_ADAPTER_MISSING", "Motion action requires a MoveIt motion adapter");
  }
  if (!target_policy_) {
    return planningFailure(ActionStatus::FAILED, FailureCategory::CONFIGURATION,
      "TARGET_POLICY_MISSING", "Motion action requires a target policy");
  }
  if (!observation.snapshot) {
    return planningFailure(ActionStatus::FAILED, FailureCategory::OBSERVATION,
      "MOTION_OBSERVATION_MISSING", "Motion planning requires a current world observation");
  }

  const auto target = target_policy_->targetPose(current_state, next_state, observation);
  if (!target.target_pose) {
    const auto failure = target.failure.value_or(Failure{FailureCategory::CONFIGURATION,
          "TARGET_POLICY_FAILED", "Target policy did not return a motion target", {}});
    return {{ActionStatus::FAILED, failure}, nullptr};
  }
  if (config_.no_op_if_postcondition_satisfied &&
    config_.state == State::RECOVER_RETREAT &&
    recoveryRetreatPostconditionSatisfied(*observation.snapshot, *target.target_pose))
  {
    return noOpPlan(config_, observation.snapshot->tcp_pose_world);
  }
  return adapter_->plan(
    {current_state, next_state, config_.kind, config_.carrying, *target.target_pose},
    observation);
}

ActionResult MotionStateAction::execute(const ExecutionContext & context)
{
  if (context.state != config_.state || context.next_state != config_.next_state) {
    return executionFailure("MOTION_TRANSITION_NOT_EXECUTABLE",
      "Motion executor received a transition other than its configured transition");
  }
  if (!adapter_) {
    return {ActionStatus::FAILED, Failure{FailureCategory::CONFIGURATION,
        "MOTION_ADAPTER_MISSING", "Motion action requires a MoveIt motion adapter", {}}};
  }
  const auto evidence = std::dynamic_pointer_cast<const MotionPlanEvidence>(context.plan);
  if (!evidence || evidence->state != config_.state ||
    evidence->next_state != config_.next_state || evidence->kind != config_.kind ||
    evidence->carrying != config_.carrying)
  {
    return executionFailure("INVALID_MOTION_PLAN_ARTIFACT",
      "Motion execution requires typed evidence for its configured transition");
  }
  if (evidence->no_op) {
    if (!config_.no_op_if_postcondition_satisfied ||
      config_.state != State::RECOVER_RETREAT ||
      !recoveryRetreatPostconditionSatisfied(context.before, evidence->end_tcp_pose))
    {
      return executionFailure("INVALID_MOTION_NO_OP_EVIDENCE",
        "Recovery motion no-op is allowed only when its complete postcondition holds");
    }
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }
  return adapter_->execute(*evidence);
}

ActionResult MotionStateAction::cancel()
{
  if (!adapter_) {
    return {ActionStatus::FAILED, Failure{FailureCategory::CONFIGURATION,
        "MOTION_ADAPTER_MISSING", "Motion action requires a MoveIt motion adapter", {}}};
  }
  return adapter_->cancel();
}

}  // namespace panda_gazebo_demo::pick_place
