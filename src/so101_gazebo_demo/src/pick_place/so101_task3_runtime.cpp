#include "so101_gazebo_demo/pick_place/so101_task3_runtime.hpp"

#include <array>
#include <chrono>
#include <cmath>
#include <string>
#include <thread>
#include <utility>

#include "so101_gazebo_demo/pick_place/moveit_scene_executor.hpp"
#include "so101_gazebo_demo/pick_place/so101_attachment_contracts.hpp"
#include "so101_gazebo_demo/pick_place/so101_gripper_state.hpp"
#include "so101_gazebo_demo/pick_place/so101_recovery_policy.hpp"
#include "so101_gazebo_demo/pick_place/transition_table.hpp"

namespace so101_gazebo_demo::pick_place
{
namespace
{

class AttachThenHoldGripper final : public IStateExecutor
{
public:
  AttachThenHoldGripper(std::shared_ptr<IStateExecutor> attach,
                        std::shared_ptr<ISO101GripperCommand> gripper, std::string gripper_joint,
                        double carry_hold_q6, double settle_seconds) :
      attach_(std::move(attach)), gripper_(std::move(gripper)),
      gripper_joint_(std::move(gripper_joint)), carry_hold_q6_(carry_hold_q6),
      settle_seconds_(settle_seconds)
  {
  }

  ActionResult execute(const ExecutionContext & context) override
  {
    auto attached = attach_->execute(context);
    if (attached.status != ActionStatus::SUCCEEDED)
      return attached;
    const auto measured_q6 = context.before.joint_positions.find(gripper_joint_);
    if (measured_q6 == context.before.joint_positions.end() ||
        !std::isfinite(measured_q6->second)) {
      return {ActionStatus::FAILED,
              Failure{FailureCategory::OBSERVATION,
                      "CARRY_HOLD_Q6_UNAVAILABLE",
                      "A finite measured gripper position is required after Gazebo attachment",
                      {}}};
    }
    // The bounded regrasp may finish slightly deeper than the calibrated cup
    // wall target.  Once the Gazebo joint owns the cup, retarget the controller
    // to the calibrated carry value instead of preserving that transient
    // squeeze; otherwise an unusually deep regrasp can violate the native-pad
    // interference ceiling at the attachment boundary.
    auto held = gripper_->command(carry_hold_q6_);
    // Gazebo's DetachableJoint can oppose the gripper position controller
    // immediately after attachment.  The hold command is advisory at this
    // boundary: defer only the controller's contact-stop abort and let the
    // attachment transition contract prove bilateral, bounded, stationary
    // grasp evidence from the fresh post-state.
    if (held.status == ActionStatus::FAILED && held.failure &&
        held.failure->code == "GRIPPER_ACTION_ABORTED") {
      held = {ActionStatus::SUCCEEDED, std::nullopt};
    }
    if (held.status == ActionStatus::SUCCEEDED && settle_seconds_ > 0.0) {
      std::this_thread::sleep_for(std::chrono::duration<double>(settle_seconds_));
    }
    return held;
  }

  ActionResult cancel() override
  {
    const auto gripper_cancelled = gripper_->cancelAndWait();
    const auto attach_cancelled = attach_->cancel();
    return gripper_cancelled.status == ActionStatus::SUCCEEDED ? attach_cancelled
                                                               : gripper_cancelled;
  }

private:
  std::shared_ptr<IStateExecutor> attach_;
  std::shared_ptr<ISO101GripperCommand> gripper_;
  std::string gripper_joint_;
  double carry_hold_q6_;
  double settle_seconds_;
};

void registerGripper(SO101Task3Runtime & runtime,
                     const SO101Task3RuntimeDependencies & dependencies,
                     const SO101Profile & profile)
{
  const std::array<SO101GripperStateConfig, 4> configs{{
    {State::PREPARE_OPEN_GRIPPER, SO101GripperTarget::PREOPEN, false},
    {State::CLOSE_GRIPPER, SO101GripperTarget::CONTACT, false},
    {State::OPEN_GRIPPER, SO101GripperTarget::FULL_OPEN, false},
    {State::RECOVER_OPEN_GRIPPER, SO101GripperTarget::FULL_OPEN, true},
  }};
  for (const auto & config : configs) {
    if (dependencies.gripper) {
      runtime.actions.registerExecutor(
        config.state, std::make_shared<SO101GripperStateExecutor>(
                        dependencies.gripper, config, profile, dependencies.gripper_observer));
    }
    const auto next = TransitionTable::resolve(config.state, ActionStatus::SUCCEEDED);
    runtime.contracts.registerContract({config.state, next},
                                       makeSO101GripperContract(config, profile));
  }
}

void registerGazebo(SO101Task3Runtime & runtime, const SO101Task3RuntimeDependencies & dependencies,
                    const SO101Profile & profile)
{
  if (dependencies.gazebo_attach) {
    if (dependencies.gripper) {
      runtime.actions.registerExecutor(
        State::ATTACH_GAZEBO,
        std::make_shared<AttachThenHoldGripper>(dependencies.gazebo_attach, dependencies.gripper,
                                                profile.gripper_joint, profile.q6_contact,
                                                profile.post_attach_hold_settle_seconds));
    } else {
      runtime.actions.registerExecutor(State::ATTACH_GAZEBO, dependencies.gazebo_attach);
    }
  }
  if (dependencies.gazebo_detach) {
    runtime.actions.registerExecutor(State::DETACH_GAZEBO, dependencies.gazebo_detach);
  }
  if (dependencies.recovery_gazebo_detach) {
    runtime.actions.registerExecutor(State::RECOVER_DETACH_GAZEBO,
                                     dependencies.recovery_gazebo_detach);
  }
}

void registerMoveItScene(SO101Task3Runtime & runtime,
                         const SO101Task3RuntimeDependencies & dependencies,
                         const SO101Task3RuntimeConfig & config)
{
  if (!dependencies.moveit_scene) {
    return;
  }
  const MoveItAttachmentSpec attachment{config.profile.moveit_attach_link,
                                        config.profile.moveit_touch_links};
  const std::array<MoveItSceneConfig, 5> configs{{
    {State::ATTACH_MOVEIT, MoveItSceneOperation::ATTACH, false, config.profile.task_object_id},
    {State::DETACH_MOVEIT, MoveItSceneOperation::DETACH, false, config.profile.task_object_id},
    {State::SYNC_WORLD_OBJECT, MoveItSceneOperation::SYNC, false, config.profile.task_object_id},
    {State::RECOVER_DETACH_MOVEIT, MoveItSceneOperation::DETACH, true,
     config.profile.task_object_id},
    {State::RECOVER_SYNC_WORLD_OBJECT, MoveItSceneOperation::SYNC, true,
     config.profile.task_object_id},
  }};
  for (const auto & scene_config : configs) {
    runtime.actions.registerExecutor(
      scene_config.state,
      std::make_shared<MoveItSceneExecutor>(dependencies.moveit_scene, scene_config, attachment,
                                            config.planning_scene_timeout_seconds,
                                            config.state_poll_interval_seconds));
  }
}

}  // namespace

SO101Task3Runtime makeSO101Task3Runtime(const SO101Task3RuntimeDependencies & dependencies,
                                        SO101Task3RuntimeConfig config)
{
  SO101Task3Runtime runtime;
  registerGripper(runtime, dependencies, config.profile);
  registerGazebo(runtime, dependencies, config.profile);
  registerMoveItScene(runtime, dependencies, config);
  registerSO101AttachmentContracts(runtime.contracts, config.profile, config.object,
                                   config.grasp_contact);
  runtime.recovery_policy = std::make_shared<SO101RecoveryPolicy>(std::move(config.profile));
  return runtime;
}

}  // namespace so101_gazebo_demo::pick_place
