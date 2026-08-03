#pragma once

#include <memory>

#include "so101_gazebo_demo/pick_place/follow_joint_trajectory_gripper_adapter.hpp"
#include "so101_gazebo_demo/pick_place/moveit_scene_adapter.hpp"
#include "so101_gazebo_demo/pick_place/recovery_policy.hpp"
#include "so101_gazebo_demo/pick_place/so101_profile.hpp"
#include "so101_gazebo_demo/pick_place/state_action.hpp"
#include "so101_gazebo_demo/pick_place/transition_contract.hpp"

namespace so101_gazebo_demo::pick_place
{

struct SO101Task3RuntimeDependencies
{
  std::shared_ptr<ISO101GripperCommand> gripper;
  std::shared_ptr<IMoveItSceneAdapter> moveit_scene;
  std::shared_ptr<IStateExecutor> gazebo_attach;
  std::shared_ptr<IStateExecutor> gazebo_detach;
  std::shared_ptr<IStateExecutor> recovery_gazebo_detach;
  std::shared_ptr<IWorldObserver> gripper_observer;
};

struct SO101Task3RuntimeConfig
{
  SO101Profile profile{SO101Profile::canonical()};
  TaskObjectConfig object;
  GraspContactValidationConfig grasp_contact;
  double planning_scene_timeout_seconds{2.0};
  double state_poll_interval_seconds{0.05};
};

struct SO101Task3Runtime
{
  StateActionRegistry actions;
  TransitionContractRegistry contracts;
  std::shared_ptr<const IRecoveryPolicy> recovery_policy;
};

[[nodiscard]] SO101Task3Runtime
makeSO101Task3Runtime(const SO101Task3RuntimeDependencies & dependencies,
                      SO101Task3RuntimeConfig config = {});

}  // namespace so101_gazebo_demo::pick_place
