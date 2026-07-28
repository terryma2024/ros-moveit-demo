#include "so101_gazebo_demo/pick_place/so101_task3_runtime.hpp"

#include <array>
#include <chrono>
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
                        std::shared_ptr<ISO101GripperCommand> gripper, double hold_q6,
                        double settle_seconds) :
    attach_(std::move(attach)), gripper_(std::move(gripper)), hold_q6_(hold_q6),
    settle_seconds_(settle_seconds)
  {
  }

  ActionResult execute(const ExecutionContext & context) override
  {
    const auto attached = attach_->execute(context);
    if (attached.status != ActionStatus::SUCCEEDED) return attached;
    const auto held = gripper_->command(hold_q6_);
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
  double hold_q6_;
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
        config.state,
        std::make_shared<SO101GripperStateExecutor>(dependencies.gripper, config, profile));
    }
    const auto next = TransitionTable::resolve(config.state, ActionStatus::SUCCEEDED);
    runtime.contracts.registerContract({config.state, next},
                                       makeSO101GripperContract(config, profile));
  }
}

void registerGazebo(SO101Task3Runtime & runtime,
                    const SO101Task3RuntimeDependencies & dependencies,
                    const SO101Profile & profile)
{
  if (dependencies.gazebo_attach) {
    if (dependencies.gripper) {
      runtime.actions.registerExecutor(
        State::ATTACH_GAZEBO,
        std::make_shared<AttachThenHoldGripper>(
          dependencies.gazebo_attach, dependencies.gripper, profile.q6_contact,
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
    {State::ATTACH_MOVEIT, MoveItSceneOperation::ATTACH, false},
    {State::DETACH_MOVEIT, MoveItSceneOperation::DETACH, false},
    {State::SYNC_WORLD_OBJECT, MoveItSceneOperation::SYNC, false},
    {State::RECOVER_DETACH_MOVEIT, MoveItSceneOperation::DETACH, true},
    {State::RECOVER_SYNC_WORLD_OBJECT, MoveItSceneOperation::SYNC, true},
  }};
  for (const auto & scene_config : configs) {
    runtime.actions.registerExecutor(
      scene_config.state,
      std::make_shared<MoveItSceneExecutor>(
        dependencies.moveit_scene, scene_config, attachment,
        config.planning_scene_timeout_seconds, config.state_poll_interval_seconds));
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
  registerSO101AttachmentContracts(runtime.contracts, config.profile);
  runtime.recovery_policy = std::make_shared<SO101RecoveryPolicy>(std::move(config.profile));
  return runtime;
}

}  // namespace so101_gazebo_demo::pick_place
