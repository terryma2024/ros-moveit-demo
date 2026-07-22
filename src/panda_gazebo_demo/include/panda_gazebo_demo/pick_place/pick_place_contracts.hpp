#pragma once

#include <memory>

#include "panda_gazebo_demo/pick_place/pick_place_target_policy.hpp"
#include "panda_gazebo_demo/pick_place/state_validation.hpp"
#include "panda_gazebo_demo/pick_place/transition_contract.hpp"

namespace panda_gazebo_demo::pick_place
{

struct PickPlaceContractConfig
{
  double tcp_position_tolerance{0.005};
  double tcp_orientation_tolerance_rad{0.035};
  double coke_position_tolerance{0.003};
  double coke_orientation_tolerance_rad{0.035};
  double carried_relative_position_tolerance{0.003};
  double carried_relative_orientation_tolerance_rad{0.035};
  GripperLimits gripper{};
};

using Contract = TransitionContractRegistry::ITransitionContract;
using TargetPolicyPtr = std::shared_ptr<const PickPlaceTargetPolicy>;

[[nodiscard]] std::shared_ptr<const Contract> makeCloseToGazeboAttachContract(
  TargetPolicyPtr target_policy, PickPlaceContractConfig config);
[[nodiscard]] std::shared_ptr<const Contract> makeGazeboToMoveItAttachContract(
  PickPlaceContractConfig config);
[[nodiscard]] std::shared_ptr<const Contract> makeMoveItAttachToLiftContract(
  PickPlaceContractConfig config);
[[nodiscard]] std::shared_ptr<const Contract> makeLiftToMoveAbovePlaceContract(
  TargetPolicyPtr target_policy, PickPlaceContractConfig config);
[[nodiscard]] std::shared_ptr<const Contract> makeMoveAbovePlaceToDescendContract(
  TargetPolicyPtr target_policy, PickPlaceContractConfig config);
[[nodiscard]] std::shared_ptr<const Contract> makeDescendPlaceToOpenContract(
  TargetPolicyPtr target_policy, PickPlaceContractConfig config);
[[nodiscard]] std::shared_ptr<const Contract> makeOpenToGazeboDetachContract(
  TargetPolicyPtr target_policy, PickPlaceContractConfig config);
[[nodiscard]] std::shared_ptr<const Contract> makeGazeboToMoveItDetachContract(
  TargetPolicyPtr target_policy, PickPlaceContractConfig config);
[[nodiscard]] std::shared_ptr<const Contract> makeMoveItDetachToSyncContract(
  TargetPolicyPtr target_policy, PickPlaceContractConfig config);
[[nodiscard]] std::shared_ptr<const Contract> makeSyncToRetreatContract(
  TargetPolicyPtr target_policy, PickPlaceContractConfig config);
[[nodiscard]] std::shared_ptr<const Contract> makeRetreatToDoneContract(
  TargetPolicyPtr target_policy, PickPlaceContractConfig config);

void registerPickPlaceForwardContracts(
  TransitionContractRegistry & registry, TargetPolicyPtr target_policy,
  PickPlaceContractConfig config);

}  // namespace panda_gazebo_demo::pick_place
