#pragma once

#include <map>
#include <memory>

#include "panda_gazebo_demo/pick_place/pick_place_target_policy.hpp"
#include "panda_gazebo_demo/pick_place/named_target_validation.hpp"
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
  std::map<std::string, double> ready_joint_positions;
  double ready_joint_tolerance{0.010};
  double gripper_close_position{0.0};
  double gripper_close_tolerance{0.004};
};

using Contract = TransitionContractRegistry::ITransitionContract;
using TargetPolicyPtr = std::shared_ptr<const PickPlaceTargetPolicy>;

[[nodiscard]] std::shared_ptr<const Contract>
makeCloseToGazeboAttachContract(const TargetPolicyPtr & target_policy,
                                const PickPlaceContractConfig & config);
[[nodiscard]] std::shared_ptr<const Contract>
makeGazeboToMoveItAttachContract(const PickPlaceContractConfig & config);
[[nodiscard]] std::shared_ptr<const Contract>
makeMoveItAttachToLiftContract(const PickPlaceContractConfig & config);
[[nodiscard]] std::shared_ptr<const Contract>
makeLiftToMoveAbovePlaceContract(const TargetPolicyPtr & target_policy,
                                 const PickPlaceContractConfig & config);
[[nodiscard]] std::shared_ptr<const Contract>
makeMoveAbovePlaceToDescendContract(const TargetPolicyPtr & target_policy,
                                    const PickPlaceContractConfig & config);
[[nodiscard]] std::shared_ptr<const Contract>
makeDescendPlaceToOpenContract(const TargetPolicyPtr & target_policy,
                               const PickPlaceContractConfig & config);
[[nodiscard]] std::shared_ptr<const Contract>
makeOpenToGazeboDetachContract(const TargetPolicyPtr & target_policy,
                               const PickPlaceContractConfig & config);
[[nodiscard]] std::shared_ptr<const Contract>
makeGazeboToMoveItDetachContract(const TargetPolicyPtr & target_policy,
                                 const PickPlaceContractConfig & config);
[[nodiscard]] std::shared_ptr<const Contract>
makeMoveItDetachToSyncContract(const TargetPolicyPtr & target_policy,
                               const PickPlaceContractConfig & config);
[[nodiscard]] std::shared_ptr<const Contract>
makeSyncToRetreatContract(const TargetPolicyPtr & target_policy,
                          const PickPlaceContractConfig & config);
[[nodiscard]] std::shared_ptr<const Contract>
makeRetreatToDoneContract(const TargetPolicyPtr & target_policy,
                          const PickPlaceContractConfig & config);

void registerPickPlaceForwardContracts(TransitionContractRegistry & registry,
                                       const TargetPolicyPtr & target_policy,
                                       const PickPlaceContractConfig & config);

}  // namespace panda_gazebo_demo::pick_place
