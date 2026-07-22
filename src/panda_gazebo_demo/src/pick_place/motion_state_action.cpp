#include "panda_gazebo_demo/pick_place/motion_state_action.hpp"

#include <memory>
#include <string>
#include <utility>

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
