#include "so101_gazebo_demo/pick_place/so101_task3_runtime.hpp"

#include <array>
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

void registerGripper(SO101Task3Runtime & runtime,
                     const SO101Task3RuntimeDependencies & dependencies,
                     const SO101Profile & profile)
{
  const std::array<SO101GripperStateConfig, 4> configs{{
    {State::PREPARE_OPEN_GRIPPER, SO101GripperTarget::PREOPEN, false},
    {State::CLOSE_GRIPPER, SO101GripperTarget::CONTACT, false},
    {State::OPEN_GRIPPER, SO101GripperTarget::PREOPEN, false},
    {State::RECOVER_OPEN_GRIPPER, SO101GripperTarget::PREOPEN, true},
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
                    const SO101Task3RuntimeDependencies & dependencies)
{
  if (dependencies.gazebo_attach) {
    runtime.actions.registerExecutor(State::ATTACH_GAZEBO, dependencies.gazebo_attach);
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
  registerGazebo(runtime, dependencies);
  registerMoveItScene(runtime, dependencies, config);
  registerSO101AttachmentContracts(runtime.contracts, config.profile);
  runtime.recovery_policy = std::make_shared<SO101RecoveryPolicy>(std::move(config.profile));
  return runtime;
}

}  // namespace so101_gazebo_demo::pick_place
