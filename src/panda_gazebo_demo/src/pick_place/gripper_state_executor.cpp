#include "panda_gazebo_demo/pick_place/gripper_state_executor.hpp"

#include <utility>

namespace panda_gazebo_demo::pick_place
{

namespace
{

ActionResult unsupportedState(State actual, State configured)
{
  return {ActionStatus::NOT_SUPPORTED,
          Failure{FailureCategory::GRIPPER,
                  "STATE_NOT_EXECUTABLE",
                  std::string("Gripper executor configured for ") + toString(configured) +
                    " cannot execute " + toString(actual),
                  {}}};
}

bool recoveryOpenPostconditionSatisfied(const WorldSnapshot & snapshot,
                                        const GripperLimits & limits)
{
  return snapshot.fresh && snapshot.arm_stationary &&
         snapshot.gazebo_task_object_pose_world.has_value() &&
         snapshot.gazebo_task_object_attached.has_value() &&
         snapshot.moveit_task_object_attached.has_value() &&
         snapshot.gazebo_task_object_stationary && *snapshot.gazebo_task_object_stationary &&
         validateGripperOpen(snapshot, limits).ok;
}

}  // namespace

GripperStateExecutor::GripperStateExecutor(std::shared_ptr<IGripperCommandAdapter> adapter,
                                           GripperStateConfig config, GripperLimits limits) :
    adapter_(std::move(adapter)), config_(config), limits_(limits)
{
}

ActionResult GripperStateExecutor::execute(const ExecutionContext & context)
{
  if (context.state != config_.state) {
    return unsupportedState(context.state, config_.state);
  }
  if (!adapter_) {
    return {ActionStatus::FAILED, Failure{FailureCategory::CONFIGURATION,
                                          "GRIPPER_ADAPTER_MISSING",
                                          "Gripper executor has no command adapter",
                                          {}}};
  }
  if (config_.no_op_if_already_open &&
      recoveryOpenPostconditionSatisfied(context.before, limits_)) {
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }
  return adapter_->command(config_.target_position, config_.max_effort);
}

ActionResult GripperStateExecutor::cancel()
{
  if (!adapter_) {
    return {ActionStatus::FAILED, Failure{FailureCategory::CONFIGURATION,
                                          "GRIPPER_ADAPTER_MISSING",
                                          "Gripper executor has no command adapter",
                                          {}}};
  }
  return adapter_->cancelAndWait();
}

}  // namespace panda_gazebo_demo::pick_place
