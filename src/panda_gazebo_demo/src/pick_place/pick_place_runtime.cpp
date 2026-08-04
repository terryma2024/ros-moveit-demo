#include "panda_gazebo_demo/pick_place/pick_place_runtime.hpp"
#include "panda_gazebo_demo/pick_place/panda_moveit_scene_policy.hpp"

#include <array>
#include <memory>
#include <utility>

#include "panda_gazebo_demo/pick_place/gripper_state_executor.hpp"
#include "panda_gazebo_demo/pick_place/motion_state_action.hpp"
#include "panda_gazebo_demo/pick_place/moveit_scene_executor.hpp"
#include "panda_gazebo_demo/pick_place/ready_retreat_action.hpp"
#include "panda_gazebo_demo/pick_place/recovery_contracts.hpp"

namespace panda_gazebo_demo::pick_place
{
namespace
{

constexpr std::array<MotionStateConfig, 8> kMotionConfigs{{
  {State::MOVE_ABOVE_OBJECT, State::DESCEND, MotionKind::POSE, false},
  {State::DESCEND, State::CLOSE_GRIPPER, MotionKind::CARTESIAN_DOWN, false},
  {State::LIFT, State::MOVE_ABOVE_PLACE, MotionKind::CARTESIAN_UP, true},
  {State::MOVE_ABOVE_PLACE, State::DESCEND_TO_PLACE, MotionKind::POSE, true},
  {State::DESCEND_TO_PLACE, State::OPEN_GRIPPER, MotionKind::CARTESIAN_DOWN, true},
  {State::RECOVER_LIFT_TO_SAFE_HEIGHT, State::RECOVER_MOVE_ABOVE_PICK, MotionKind::CARTESIAN_UP,
   true, true},
  {State::RECOVER_MOVE_ABOVE_PICK, State::RECOVER_DESCEND_TO_PICK, MotionKind::POSE, true, true},
  {State::RECOVER_DESCEND_TO_PICK, State::RECOVER_OPEN_GRIPPER, MotionKind::CARTESIAN_DOWN, true,
   true},
}};

void registerMotionActions(PickPlaceRuntimeRegistries & runtime,
                           const PickPlaceRuntimeDependencies & dependencies,
                           const PickPlaceRuntimeConfig & config)
{
  for (const auto & motion_config : kMotionConfigs) {
    auto action =
      std::make_shared<MotionStateAction>(dependencies.motion, config.target_policy, motion_config);
    runtime.actions.registerPlanner(motion_config.state, action);
    runtime.actions.registerExecutor(motion_config.state, action);
    runtime.plan_validators.registerValidator(
      motion_config.state, std::make_shared<MotionPlanValidator>(
                             motion_config, config.target_policy, config.motion_plan_limits));
  }
}

void registerReadyRetreatActions(PickPlaceRuntimeRegistries & runtime,
                                 const PickPlaceRuntimeDependencies & dependencies,
                                 const PickPlaceRuntimeConfig & config)
{
  if (!dependencies.motion || config.ready_joint_positions.empty()) {
    return;
  }
  for (const auto & [state, next_state] : std::array{
         std::pair{State::RETREAT, State::DONE}, std::pair{State::RECOVER_RETREAT, State::ERROR}}) {
    const ReadyRetreatConfig action_config{state,
                                           next_state,
                                           config.ready_named_target,
                                           config.ready_joint_positions,
                                           config.ready_joint_tolerance,
                                           config.gripper_close_position,
                                           config.gripper_max_effort};
    auto action = std::make_shared<ReadyRetreatAction>(dependencies.motion, dependencies.gripper,
                                                       dependencies.observer, action_config);
    runtime.actions.registerPlanner(state, action);
    runtime.plan_validators.registerValidator(state, std::make_shared<NamedTargetPlanValidator>(
                                                       state, next_state, config.ready_named_target,
                                                       config.ready_joint_positions,
                                                       config.ready_joint_tolerance));
    if (dependencies.gripper && dependencies.observer) {
      runtime.actions.registerExecutor(state, std::move(action));
    }
  }
}

void registerGripperActions(PickPlaceRuntimeRegistries & runtime,
                            const PickPlaceRuntimeDependencies & dependencies,
                            const PickPlaceRuntimeConfig & config)
{
  const std::array gripper_configs{
    GripperStateConfig{State::PREPARE_OPEN_GRIPPER, config.gripper_open_position,
                       config.gripper_max_effort, false},
    GripperStateConfig{State::CLOSE_GRIPPER, config.gripper_close_position,
                       config.gripper_max_effort, false},
    GripperStateConfig{State::OPEN_GRIPPER, config.gripper_open_position, config.gripper_max_effort,
                       false},
    GripperStateConfig{State::RECOVER_OPEN_GRIPPER, config.gripper_open_position,
                       config.gripper_max_effort, true},
  };
  for (const auto & gripper_config : gripper_configs) {
    runtime.actions.registerExecutor(
      gripper_config.state,
      std::make_shared<GripperStateExecutor>(dependencies.gripper, gripper_config, config.gripper));
  }
}

void registerGazeboActions(PickPlaceRuntimeRegistries & runtime,
                           const PickPlaceRuntimeDependencies & dependencies)
{
  runtime.actions.registerExecutor(State::ATTACH_GAZEBO, dependencies.gazebo_attach);
  runtime.actions.registerExecutor(State::DETACH_GAZEBO, dependencies.gazebo_detach);
  runtime.actions.registerExecutor(State::RECOVER_DETACH_GAZEBO,
                                   dependencies.recovery_gazebo_detach);
}

void registerMoveItSceneActions(PickPlaceRuntimeRegistries & runtime,
                                const PickPlaceRuntimeDependencies & dependencies,
                                const PickPlaceRuntimeConfig & config)
{
  const MoveItAttachmentSpec attachment{"panda_hand",
                                        {"panda_hand", "panda_leftfinger", "panda_rightfinger"}};
  const std::array scene_configs{
    MoveItSceneConfig{State::ATTACH_MOVEIT, MoveItSceneOperation::ATTACH, false, "coke", attachment,
                      config.planning_scene_timeout_seconds, config.state_poll_interval_seconds},
    MoveItSceneConfig{State::DETACH_MOVEIT, MoveItSceneOperation::DETACH, false, "coke", attachment,
                      config.planning_scene_timeout_seconds, config.state_poll_interval_seconds},
    MoveItSceneConfig{State::SYNC_WORLD_OBJECT, MoveItSceneOperation::SYNC, false, "coke",
                      attachment, config.planning_scene_timeout_seconds,
                      config.state_poll_interval_seconds},
    MoveItSceneConfig{State::RECOVER_DETACH_MOVEIT, MoveItSceneOperation::DETACH, true, "coke",
                      attachment, config.planning_scene_timeout_seconds,
                      config.state_poll_interval_seconds},
    MoveItSceneConfig{State::RECOVER_SYNC_WORLD_OBJECT, MoveItSceneOperation::SYNC, true, "coke",
                      attachment, config.planning_scene_timeout_seconds,
                      config.state_poll_interval_seconds},
  };
  for (const auto & scene_config : scene_configs) {
    runtime.actions.registerExecutor(
      scene_config.state,
      std::make_shared<MoveItSceneExecutor>(
        dependencies.moveit_scene, scene_config,
        std::make_shared<PandaMoveItScenePolicy>(config.gripper, scene_config.idempotent)));
  }
}

void registerContracts(PickPlaceRuntimeRegistries & runtime, PickPlaceRuntimeConfig config)
{
  config.contract.gripper = config.gripper;
  runtime.contracts.registerContract(
    {State::PREPARE_OPEN_GRIPPER, State::MOVE_ABOVE_OBJECT},
    std::make_shared<PrepareOpenGripperToMoveAboveObjectValidator>(
      config.required_world_objects, config.contract.tcp_position_tolerance,
      config.contract.tcp_orientation_tolerance_rad, config.contract.coke_position_tolerance,
      config.contract.coke_orientation_tolerance_rad));
  runtime.contracts.registerContract(
    {State::MOVE_ABOVE_OBJECT, State::DESCEND},
    std::make_shared<MoveAboveObjectToDescendValidator>(
      config.target_policy, config.required_world_objects, config.contract.tcp_position_tolerance,
      config.contract.tcp_orientation_tolerance_rad, config.contract.coke_position_tolerance,
      config.contract.coke_orientation_tolerance_rad));
  runtime.contracts.registerContract(
    {State::DESCEND, State::CLOSE_GRIPPER},
    std::make_shared<DescendToCloseGripperValidator>(
      config.target_policy, config.required_world_objects, config.contract.tcp_position_tolerance,
      config.contract.tcp_orientation_tolerance_rad, config.contract.coke_position_tolerance,
      config.contract.coke_orientation_tolerance_rad));
  registerPickPlaceForwardContracts(runtime.contracts, config.target_policy, config.contract);
  registerRecoveryContracts(runtime.contracts, config.target_policy, config.contract);
}

}  // namespace

PickPlaceRuntimeRegistries
makePickPlaceRuntimeRegistries(const PickPlaceRuntimeDependencies & dependencies,
                               PickPlaceRuntimeConfig config)
{
  PickPlaceRuntimeRegistries runtime;
  registerMotionActions(runtime, dependencies, config);
  registerReadyRetreatActions(runtime, dependencies, config);
  registerGripperActions(runtime, dependencies, config);
  registerGazeboActions(runtime, dependencies);
  registerMoveItSceneActions(runtime, dependencies, config);
  registerContracts(runtime, std::move(config));
  return runtime;
}

}  // namespace panda_gazebo_demo::pick_place
