#pragma once

#include <memory>
#include <vector>

#include "panda_gazebo_demo/pick_place/gripper_command_adapter.hpp"
#include "panda_gazebo_demo/pick_place/motion_plan_evidence.hpp"
#include "panda_gazebo_demo/pick_place/moveit_motion_adapter.hpp"
#include "panda_gazebo_demo/pick_place/moveit_scene_adapter.hpp"
#include "panda_gazebo_demo/pick_place/pick_place_contracts.hpp"
#include "panda_gazebo_demo/pick_place/plan_validation.hpp"
#include "panda_gazebo_demo/pick_place/state_action.hpp"
#include "panda_gazebo_demo/pick_place/transition_contract.hpp"

namespace panda_gazebo_demo::pick_place
{

struct PickPlaceRuntimeDependencies
{
  std::shared_ptr<IMoveItMotionAdapter> motion;
  std::shared_ptr<IGripperCommandAdapter> gripper;
  std::shared_ptr<IWorldObserver> observer;
  std::shared_ptr<IMoveItSceneAdapter> moveit_scene;
  std::shared_ptr<IStateExecutor> gazebo_attach;
  std::shared_ptr<IStateExecutor> gazebo_detach;
  std::shared_ptr<IStateExecutor> recovery_gazebo_detach;
};

struct PickPlaceRuntimeConfig
{
  TargetPolicyPtr target_policy;
  std::vector<std::string> required_world_objects{"table", "coke"};
  MotionPlanLimits motion_plan_limits{};
  PickPlaceContractConfig contract{};
  GripperLimits gripper{};
  double gripper_open_position{0.04};
  double gripper_close_position{0.0};
  double gripper_close_tolerance{0.004};
  double gripper_max_effort{0.0};
  std::string ready_named_target{"ready"};
  std::map<std::string, double> ready_joint_positions;
  double ready_joint_tolerance{0.010};
  double planning_scene_timeout_seconds{2.0};
  double state_poll_interval_seconds{0.05};
};

struct PickPlaceRuntimeRegistries
{
  StateActionRegistry actions;
  PlanValidatorRegistry plan_validators;
  TransitionContractRegistry contracts;
};

[[nodiscard]] PickPlaceRuntimeRegistries
makePickPlaceRuntimeRegistries(const PickPlaceRuntimeDependencies & dependencies,
                               PickPlaceRuntimeConfig config);

}  // namespace panda_gazebo_demo::pick_place
